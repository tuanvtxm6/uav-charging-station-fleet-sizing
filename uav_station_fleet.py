#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UAV charging-station placement & fleet sizing (đề 8)
====================================================
Bài toán đa mục tiêu: chọn vị trí trạm sạc, số UAV mỗi trạm và vùng phục vụ để
cực tiểu hóa (f1) thời gian phản ứng trung bình có trọng số rủi ro, (f2) năng
lượng bay, (f3) tỉ lệ rủi ro không được phủ, dưới ràng buộc pin, năng lực đội
bay và ngân sách.

Thuật toán trong file:
  * Greedy        : heuristic tham lam kiểu MCLP có xét năng lực (baseline 1)
  * MILP          : scipy/HiGHS, nghiệm tham chiếu cho instance nhỏ (baseline 2)
  * NSGA-II       : NSGA-II chuẩn + constraint-domination (baseline 3)
  * RP-MNSGA      : NSGA-II lai (memetic) có risk-priority repair, local search
                    và khởi tạo từ greedy (đề xuất) + 3 biến thể ablation

Cách dùng:
  python uav_station_fleet.py demo                # chạy nhanh 1 instance
  python uav_station_fleet.py experiment          # toàn bộ thực nghiệm
  python uav_station_fleet.py experiment --quick  # bản rút gọn để kiểm tra
  python uav_station_fleet.py plots               # vẽ lại hình từ results/raw.pkl
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import pickle
import time
from dataclasses import dataclass, replace
from multiprocessing import Pool

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "results")
REF = 1.1  # điểm tham chiếu hypervolume trong không gian đã chuẩn hóa


# ----------------------------------------------------------------------------
# 1. Instance
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Params:
    box_km: float = 30.0      # cạnh dài vùng nghiên cứu sau khi co giãn tọa độ
    speed: float = 60.0       # km/h
    range_km: float = 12.0    # tầm bay khứ hồi R (bán kính phục vụ = R/2)
    wh_per_km: float = 25.0   # năng lượng tiêu thụ
    recharge_h: float = 0.5   # thời gian sạc sau mỗi nhiệm vụ
    horizon_h: float = 8.0    # chu kỳ hoạt động T
    c_station: float = 10.0   # chi phí mở trạm
    c_uav: float = 2.0        # chi phí một UAV
    u_max: int = 6            # sức chứa tối đa của trạm
    q_levels: int = 4         # số mức bán kính phục vụ (q/q_levels * R/2)
    beta: float = 0.30        # mức ngân sách (tỉ lệ so với cấu hình "đầy đủ")
    inst_seed: int = 2026     # seed sinh trọng số rủi ro, tần suất, ứng viên


def load_tsplib(name: str) -> np.ndarray:
    """Đọc NODE_COORD_SECTION của file TSPLIB (EUC_2D)."""
    pts, on = [], False
    with open(os.path.join(DATA, name + ".tsp"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("NODE_COORD_SECTION"):
                on = True
                continue
            if not on or not line or line == "EOF":
                continue
            parts = line.split()
            pts.append((float(parts[1]), float(parts[2])))
    return np.array(pts)


class Sol:
    """Một lời giải đã giải mã."""
    __slots__ = ("n", "q", "f", "cost", "viol", "used", "risk", "assign")

    def __init__(self, n, q, f, cost, viol, used, risk, assign):
        self.n, self.q, self.f, self.cost, self.viol = n, q, f, cost, viol
        self.used, self.risk, self.assign = used, risk, assign

    @property
    def key(self):   # bán kính của trạm đóng không ảnh hưởng lời giải
        return self.n, tuple(b if a else 0 for a, b in zip(self.n, self.q))


class Instance:
    def __init__(self, name: str, p: Params = Params()):
        self.name, self.p = name, p
        rng = np.random.default_rng(p.inst_seed)
        xy = load_tsplib(name)
        xy = xy - xy.min(0)
        xy = xy / xy.max() * p.box_km
        self.xy = xy
        self.I = I = len(xy)
        self.J = J = int(min(max(15, I // 4), 120))
        self.cand = np.sort(rng.choice(I, J, replace=False))  # vị trí ứng viên
        # trọng số rủi ro: 3 "điểm nóng" Gauss -> w trong [1, 10]
        hot = xy[rng.choice(I, 3, replace=False)]
        g = np.exp(-((xy[:, None, :] - hot[None]) ** 2).sum(2)
                   / (2 * (0.18 * p.box_km) ** 2)).sum(1)
        self.w = 1.0 + 9.0 * g / g.max()
        self.lam = rng.integers(1, 6, I).astype(float)  # số nhiệm vụ / chu kỳ
        self.W = float(self.w.sum())
        d = np.sqrt(((xy[:, None, :] - xy[self.cand][None]) ** 2).sum(2))
        self.d = d
        self.T = p.horizon_h
        # near[i]: các trạm trong tầm bay, gần -> xa:
        #   (j, thời gian chiếm dụng, thời gian phản ứng [phút], năng lượng [Wh])
        self.near = []
        for i in range(I):
            js = [j for j in np.argsort(d[i]) if 2 * d[i, j] <= p.range_km]
            self.near.append([(int(j),
                               float(self.lam[i] * (2 * d[i, j] / p.speed + p.recharge_h)),
                               float(d[i, j] / p.speed * 60.0),
                               float(self.lam[i] * 2 * p.wh_per_km * d[i, j]))
                              for j in js])
        self.order = [int(i) for i in np.argsort(-self.w)]  # ưu tiên rủi ro cao
        self.wl = self.w.tolist()
        need = float(self.lam.sum()) * (p.range_km / (2 * p.speed) + p.recharge_h) / self.T
        self.B = float(round(p.beta * (p.c_station * J + p.c_uav * need)))
        self.t_max = p.range_km / 2 / p.speed * 60.0
        self.e_max = float(self.lam.sum()) * p.wh_per_km * p.range_km
        self.coverable = float(sum(self.w[i] for i in range(I) if self.near[i])) / self.W
        self.evals = 0

    # ---- chi phí & giải mã ---------------------------------------------------
    def cost(self, n) -> float:
        return self.p.c_station * sum(1 for x in n if x) + self.p.c_uav * sum(n)

    def decode(self, n, q=None) -> Sol:
        """Gán vùng phục vụ: duyệt điểm theo rủi ro giảm dần, gán vào trạm gần
        nhất còn năng lực và có bán kính phục vụ (mức q_j) chứa điểm đó.
        Mỗi lần gọi = 1 lần đánh giá."""
        self.evals += 1
        T = self.T
        J = self.J
        L = self.p.q_levels
        if q is None:
            q = [L] * J
        lim = [x * self.t_max / L + 1e-9 for x in q]
        cap = [x * T for x in n]
        used = [0.0] * J
        risk = [0.0] * J
        assign = [-1] * self.I
        swt = cw = en = 0.0
        near, wl = self.near, self.wl
        for i in self.order:
            for j, mt, tij, eij in near[i]:
                if tij <= lim[j] and cap[j] - used[j] >= mt - 1e-9:
                    used[j] += mt
                    wi = wl[i]
                    risk[j] += wi
                    assign[i] = j
                    swt += wi * tij
                    cw += wi
                    en += eij
                    break
        f1 = swt / cw if cw > 0 else 0.0
        c = self.cost(n)
        return Sol(tuple(n), tuple(q), (f1, en, 1.0 - cw / self.W), c,
                   max(0.0, c - self.B), used, risk, assign)

    def normalize(self, F) -> np.ndarray:
        F = np.atleast_2d(np.asarray(F, float))
        return F / np.array([self.t_max, self.e_max, 1.0])

    # ---- các phép toán dùng chung cho greedy / repair / local search ---------
    def trim(self, s: Sol) -> Sol:
        """Bỏ UAV nhàn rỗi: không đổi mục tiêu, giảm chi phí."""
        n = [int(math.ceil(u / self.T - 1e-9)) for u in s.used]
        s.n = tuple(n)
        s.cost = self.cost(n)
        s.viol = max(0.0, s.cost - self.B)
        return s

    def addition_scores(self, s: Sol):
        """Lợi ích biên ước lượng khi thêm 1 UAV (hoặc mở trạm mới 1 UAV) tại j:
        rủi ro chưa phủ trong tầm bay mà năng lực mới chứa được, chia chi phí."""
        T, p = self.T, self.p
        n = s.n
        lim = [x * self.t_max / p.q_levels + 1e-9 for x in s.q]
        room = [n[j] * T - s.used[j] + T for j in range(self.J)]
        gain = [0.0] * self.J
        for i in self.order:
            if s.assign[i] >= 0:
                continue
            wi = self.wl[i]
            for j, mt, tij, _ in self.near[i]:
                if tij <= lim[j] and room[j] >= mt:
                    room[j] -= mt
                    gain[j] += wi
        slack = self.B - s.cost
        out = []
        for j in range(self.J):
            if gain[j] <= 0 or n[j] >= p.u_max:
                continue
            c = p.c_uav if n[j] > 0 else p.c_station + p.c_uav
            if c <= slack + 1e-9:
                out.append((gain[j] / c, j))
        out.sort(reverse=True)
        return out

    def drop_to_budget(self, s: Sol):
        """Risk-priority repair khi vượt ngân sách: loại phần tử có rủi ro phủ
        trên chi phí thấp nhất cho tới khi khả thi."""
        p = self.p
        n = list(s.n)
        risk = list(s.risk)
        cost = self.cost(n)
        while cost > self.B + 1e-9:
            opened = [j for j in range(self.J) if n[j] > 0]
            if cost - self.B <= 2 * p.c_uav:      # vượt ít: bớt 1 UAV
                j = min(opened, key=lambda k: risk[k] / n[k])
                risk[j] *= (n[j] - 1) / n[j]
                n[j] -= 1
            else:                                  # vượt nhiều: đóng 1 trạm
                j = min(opened, key=lambda k: risk[k] / (p.c_station + p.c_uav * n[k]))
                n[j] = 0
                risk[j] = 0.0
            cost = self.cost(n)
        return n


# ----------------------------------------------------------------------------
# 2. Chỉ số chất lượng
# ----------------------------------------------------------------------------
def nondominated(F: np.ndarray) -> np.ndarray:
    """Mặt nạ các điểm không bị trội (cực tiểu hóa)."""
    F = np.asarray(F, float)
    keep = np.ones(len(F), bool)
    for i in range(len(F)):
        if not keep[i]:
            continue
        dom = (F <= F[i]).all(1) & (F < F[i]).any(1)
        if dom.any():
            keep[i] = False
    return keep


def _area2d(pts, ref):
    area, prev = 0.0, ref
    for x, y in sorted(pts):
        if y < prev:
            area += (ref - x) * (prev - y)
            prev = y
    return area


def hypervolume(Fn: np.ndarray, ref: float = REF) -> float:
    """Hypervolume 3 chiều chính xác (quét theo f3)."""
    P = np.asarray(Fn, float)
    if len(P) == 0:
        return 0.0
    P = P[(P < ref).all(1)]
    if len(P) == 0:
        return 0.0
    P = P[np.argsort(P[:, 2])]
    hv, layer = 0.0, []
    for k in range(len(P)):
        layer.append((P[k, 0], P[k, 1]))
        z_next = P[k + 1, 2] if k + 1 < len(P) else ref
        if z_next > P[k, 2]:
            hv += _area2d(layer, ref) * (z_next - P[k, 2])
    return hv


def igd(Fn: np.ndarray, ref_front: np.ndarray) -> float:
    if len(Fn) == 0:
        return float("inf")
    d = np.sqrt(((ref_front[:, None, :] - Fn[None]) ** 2).sum(2))
    return float(d.min(1).mean())


# ----------------------------------------------------------------------------
# 3. Baseline: Greedy và MILP
# ----------------------------------------------------------------------------
def greedy(inst: Instance):
    """Mỗi bước thêm 1 UAV / mở 1 trạm có lợi ích biên trên chi phí lớn nhất.
    Trả về toàn bộ quỹ đạo (mỗi bước là một lời giải ở mức ngân sách thấp hơn)."""
    n = [0] * inst.J
    s = inst.decode(n)
    path = [s]
    while True:
        cand = inst.addition_scores(s)
        if not cand:
            break
        n = list(s.n)
        n[cand[0][1]] += 1
        s = inst.trim(inst.decode(n))      # greedy luôn dùng bán kính tối đa
        path.append(s)
    return path


def milp_reference(inst: Instance, deltas=(0.05, 0.15, 0.30), time_limit=120.0):
    """MILP: (a) min f3 dưới ngân sách -> f3*; (b) min f2 với f3 <= f3* + delta."""
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import lil_matrix

    p, J, I = inst.p, inst.J, inst.I
    pairs = [(i, j, mt, e) for i in range(I) for j, mt, _, e in inst.near[i]]
    P = len(pairs)
    nv = 2 * J + P                       # y_j | n_j | x_ij
    A = lil_matrix((I + 2 * J + 1, nv))
    lo = np.full(I + 2 * J + 1, -np.inf)
    hi = np.zeros(I + 2 * J + 1)
    for k, (i, j, mt, _) in enumerate(pairs):
        A[i, 2 * J + k] = 1.0            # mỗi điểm gán tối đa 1 trạm
        A[I + j, 2 * J + k] = mt         # năng lực: sum mt*x <= T*n_j
    hi[:I] = 1.0
    for j in range(J):
        A[I + j, J + j] = -inst.T
        A[I + J + j, J + j] = 1.0        # n_j <= Umax*y_j
        A[I + J + j, j] = -p.u_max
        A[I + 2 * J, j] = p.c_station    # ngân sách
        A[I + 2 * J, J + j] = p.c_uav
    hi[I + 2 * J] = inst.B
    A = A.tocsr()
    ub = np.concatenate([np.ones(J), np.full(J, p.u_max), np.ones(P)])
    bounds = Bounds(np.zeros(nv), ub)
    integ = np.ones(nv)
    wvec = np.zeros(nv)
    evec = np.zeros(nv)
    for k, (i, j, _, e) in enumerate(pairs):
        wvec[2 * J + k] = inst.w[i]
        evec[2 * J + k] = e
    opts = {"time_limit": time_limit, "mip_rel_gap": 1e-6}
    out = {"instance": inst.name, "vars": int(nv), "points": []}
    t0 = time.time()
    r = milp(-wvec, constraints=LinearConstraint(A, lo, hi), integrality=integ,
             bounds=bounds, options=opts)
    f3_star = 1.0 - float(wvec @ r.x) / inst.W
    out.update(f3_star=f3_star, f3_status=int(r.status), f3_time=time.time() - t0)
    from scipy.sparse import csr_matrix, vstack
    for eps in [round(f3_star + dl, 4) for dl in deltas]:
        if eps >= 1.0:
            continue
        A2 = vstack([A, csr_matrix(wvec)])
        lo2 = np.append(lo, (1.0 - eps) * inst.W)
        hi2 = np.append(hi, np.inf)
        t0 = time.time()
        r2 = milp(evec, constraints=LinearConstraint(A2, lo2, hi2), integrality=integ,
                  bounds=bounds, options=opts)
        if r2.x is None:
            continue
        out["points"].append({"eps": eps, "f2": float(evec @ r2.x),
                              "f3": 1.0 - float(wvec @ r2.x) / inst.W,
                              "status": int(r2.status), "time": time.time() - t0})
    return out


# ----------------------------------------------------------------------------
# 4. NSGA-II và RP-MNSGA
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Cfg:
    repair: bool = True      # risk-priority repair (trim / drop / fill)
    ls: bool = True          # local search (memetic)
    seed_init: bool = True   # khởi tạo một phần quần thể từ greedy
    p_fill: float = 0.5      # xác suất dùng ngân sách dư để phủ thêm rủi ro
    ls_k: int = 5            # số cá thể front 1 được local search mỗi thế hệ
    ls_steps: int = 3
    pc: float = 0.9
    seed_frac: float = 0.2


ALGOS = {
    "NSGA-II": Cfg(repair=False, ls=False, seed_init=False),
    "RP-MNSGA": Cfg(),
    "w/o repair": Cfg(repair=False),
    "w/o LS": Cfg(ls=False),
    "w/o seeding": Cfg(seed_init=False),
}


def rank_and_crowd(F: np.ndarray, V: np.ndarray):
    """Fast non-dominated sort với constraint-domination + crowding distance."""
    N = len(F)
    le = (F[:, None, :] <= F[None, :, :]).all(2)
    lt = (F[:, None, :] < F[None, :, :]).any(2)
    feas = V <= 0
    D = ((feas[:, None] & feas[None, :] & le & lt)
         | (feas[:, None] & ~feas[None, :])
         | (~feas[:, None] & ~feas[None, :] & (V[:, None] < V[None, :])))
    ndom = D.sum(0)
    rank = np.full(N, -1)
    r = 0
    while (rank < 0).any():
        front = np.where((ndom == 0) & (rank < 0))[0]
        rank[front] = r
        ndom = ndom - D[front].sum(0)
        ndom[front] = -1
        r += 1
    crowd = np.zeros(N)
    for r in range(rank.max() + 1):
        idx = np.where(rank == r)[0]
        if len(idx) <= 2:
            crowd[idx] = np.inf
            continue
        for m in range(F.shape[1]):
            o = idx[np.argsort(F[idx, m])]
            span = F[o[-1], m] - F[o[0], m]
            crowd[o[0]] = crowd[o[-1]] = np.inf
            if span > 0:
                crowd[o[1:-1]] += (F[o[2:], m] - F[o[:-2], m]) / span
    return rank, crowd


class MOEA:
    def __init__(self, inst: Instance, cfg: Cfg, seed: int, pop_size=100, max_evals=20000):
        self.inst, self.cfg = inst, cfg
        self.rng = np.random.default_rng(seed)
        self.N, self.max_evals = pop_size, max_evals
        self.scale = np.array([inst.t_max, inst.e_max, 1.0])

    # ---- đánh giá (+ repair) -------------------------------------------------
    def evaluate(self, n, q) -> Sol:
        inst = self.inst
        s = inst.decode(n, q)
        if not self.cfg.repair:
            return s
        inst.trim(s)
        if s.viol > 0:                                   # vượt ngân sách
            s = inst.trim(inst.decode(inst.drop_to_budget(s), q))
        elif self.rng.random() < self.cfg.p_fill:        # còn dư ngân sách
            cand = inst.addition_scores(s)
            if cand:
                j = cand[int(self.rng.integers(min(3, len(cand))))][1]
                n2 = list(s.n)
                n2[j] += 1
                s = inst.trim(inst.decode(n2, q))
        return s

    # ---- toán tử biến dị -----------------------------------------------------
    def random_chrom(self):
        J, um = self.inst.J, self.inst.p.u_max
        p_open = self.rng.uniform(0.05, 0.6)
        n = self.rng.integers(1, um + 1, J)
        n[self.rng.random(J) >= p_open] = 0
        return n.tolist(), self.rng.integers(1, self.inst.p.q_levels + 1, J).tolist()

    def vary(self, pa: Sol, pb: Sol):
        """Lai đồng nhất theo trạm (giữ cặp n_j, q_j) + đột biến từng gen."""
        J, um, rng = self.inst.J, self.inst.p.u_max, self.rng
        L = self.inst.p.q_levels
        a, b = np.array(pa.n), np.array(pb.n)
        qa, qb = np.array(pa.q), np.array(pb.q)
        if rng.random() < self.cfg.pc:
            m = rng.random(J) < 0.5
            a, b = np.where(m, a, b), np.where(m, b, a)
            qa, qb = np.where(m, qa, qb), np.where(m, qb, qa)
        for c, qc in ((a, qa), (b, qb)):
            for j in np.where(rng.random(J) < 1.0 / J)[0]:
                if c[j] == 0:
                    c[j] = rng.integers(1, um + 1)
                else:
                    u = rng.random()
                    c[j] = 0 if u < 1 / 3 else (min(um, c[j] + 1) if u < 2 / 3 else c[j] - 1)
            for j in np.where(rng.random(J) < 1.0 / J)[0]:
                qc[j] = min(L, max(1, qc[j] + (1 if rng.random() < 0.5 else -1)))
        return (a.tolist(), qa.tolist()), (b.tolist(), qb.tolist())

    # ---- local search --------------------------------------------------------
    def neighbor(self, s: Sol):
        inst, rng, p = self.inst, self.rng, self.inst.p
        n, q = list(s.n), list(s.q)
        opened = [j for j in range(inst.J) if n[j] > 0]
        move = int(rng.integers(5))
        pick = lambda lst: lst[int(rng.integers(min(3, len(lst))))]
        if move == 0 and opened:        # relocate: dời trạm yếu sang nơi còn rủi ro
            weak = sorted(opened, key=lambda k: s.risk[k] / (p.c_station + p.c_uav * n[k]))
            a = pick(weak)
            closed = sorted((j for j in range(inst.J) if n[j] == 0),
                            key=lambda k: inst.d[inst.cand[a], k])
            if not closed:
                return None
            b = pick(closed)
            n[b], n[a], q[b] = n[a], 0, q[a]
        elif move == 1 and opened:      # shift: chuyển 1 UAV tới nơi thiếu năng lực
            a = opened[int(rng.integers(len(opened)))]
            n[a] -= 1
            tmp = Sol(tuple(n), s.q, s.f, inst.cost(n), 0.0, s.used, s.risk, s.assign)
            cand = [c for c in inst.addition_scores(tmp) if c[1] != a]
            if not cand:
                return None
            n[pick(cand)[1]] += 1
        elif move == 2 and len(opened) > 1:   # drop: đóng trạm đóng góp thấp
            weak = sorted(opened, key=lambda k: s.risk[k] / (p.c_station + p.c_uav * n[k]))
            n[pick(weak)] = 0
        elif move == 3 and opened:      # radius: co / giãn vùng phục vụ của 1 trạm
            a = opened[int(rng.integers(len(opened)))]
            q2 = min(p.q_levels, max(1, q[a] + (1 if rng.random() < 0.5 else -1)))
            if q2 == q[a]:
                return None
            q[a] = q2
        else:                           # add: thêm UAV / trạm theo lợi ích biên
            cand = inst.addition_scores(s)
            if not cand:
                return None
            n[pick(cand)[1]] += 1
        return n, q

    def local_search(self, s: Sol):
        lam = self.rng.dirichlet(np.ones(3))
        g = lambda x: float(lam @ (np.array(x.f) / self.scale))
        cur, best = s, g(s)
        for _ in range(self.cfg.ls_steps):
            n2 = self.neighbor(cur)
            if n2 is None:
                continue
            s2 = self.evaluate(*n2)
            if s2.viol <= 0 and g(s2) < best - 1e-12:
                cur, best = s2, g(s2)
        return None if cur is s else cur

    # ---- vòng lặp chính ------------------------------------------------------
    def select(self, pool):
        uniq = {}
        for s in pool:                                   # loại cá thể trùng
            uniq.setdefault(s.key, s)
        pool = list(uniq.values())
        F = np.array([s.f for s in pool]) / self.scale
        V = np.array([s.viol for s in pool])
        rank, crowd = rank_and_crowd(F, V)
        order = np.lexsort((-crowd, rank))[: self.N]
        return [pool[i] for i in order], rank[order], crowd[order]

    def front(self, pop):
        feas = [s for s in pop if s.viol <= 0]
        if not feas:
            return np.zeros((0, 3)), []
        F = np.array([s.f for s in feas])
        keep = nondominated(F)
        return F[keep], [s for s, k in zip(feas, keep) if k]

    def run(self, n_check=20):
        inst, rng, N = self.inst, self.rng, self.N
        inst.evals = 0
        t0 = time.time()
        pool = []
        if self.cfg.seed_init:
            path = greedy(inst)[1:]
            k = min(len(path), int(self.cfg.seed_frac * N))
            if k:
                pool = [path[i] for i in np.unique(np.linspace(0, len(path) - 1, k).astype(int))]
        while len(pool) < N:
            pool.append(self.evaluate(*self.random_chrom()))
        pop, rank, crowd = self.select(pool)
        hist, step = [], self.max_evals / n_check
        next_cp = step
        while inst.evals < self.max_evals:
            kids = []
            while len(kids) < N:
                i = rng.integers(len(pop), size=4)
                pa = i[0] if (rank[i[0]], -crowd[i[0]]) < (rank[i[1]], -crowd[i[1]]) else i[1]
                pb = i[2] if (rank[i[2]], -crowd[i[2]]) < (rank[i[3]], -crowd[i[3]]) else i[3]
                for c in self.vary(pop[pa], pop[pb]):
                    kids.append(self.evaluate(*c))
            if self.cfg.ls:
                first = [s for s, r in zip(pop, rank) if r == 0 and s.viol <= 0]
                if first:
                    for i in rng.choice(len(first), min(self.cfg.ls_k, len(first)), replace=False):
                        s2 = self.local_search(first[i])
                        if s2 is not None:
                            kids.append(s2)
            pop, rank, crowd = self.select(pop + kids)
            while inst.evals >= next_cp and len(hist) < n_check:
                hist.append((int(next_cp), hypervolume(inst.normalize(self.front(pop)[0]))))
                next_cp += step
        F, sols = self.front(pop)
        best = min(sols, key=lambda s: (s.f[2], s.f[0])) if sols else None
        return {"F": F, "hv": hypervolume(inst.normalize(F)) if len(F) else 0.0,
                "hist": hist, "runtime": time.time() - t0, "evals": inst.evals,
                "best_cov": None if best is None else
                {"n": list(best.n), "q": list(best.q), "f": list(best.f),
                 "assign": list(best.assign)}}


# ----------------------------------------------------------------------------
# 5. Thực nghiệm
# ----------------------------------------------------------------------------
_CACHE = {}


def get_instance(name, params: Params) -> Instance:
    key = (name, params)
    if key not in _CACHE:
        _CACHE[key] = Instance(name, params)
    return _CACHE[key]


def run_task(task):
    name, algo, seed, max_evals, pop, params, tag = task
    inst = get_instance(name, params)
    res = MOEA(inst, ALGOS[algo], seed, pop, max_evals).run()
    res.update(instance=name, algo=algo, seed=seed, tag=tag, pop=pop,
               beta=params.beta, range_km=params.range_km)
    return res


def holm(pvals):
    """Hiệu chỉnh Holm cho một nhóm p-value."""
    order = np.argsort(pvals)
    adj = np.empty(len(pvals))
    run = 0.0
    for k, i in enumerate(order):
        run = max(run, (len(pvals) - k) * pvals[i])
        adj[i] = min(1.0, run)
    return adj


def experiment(quick=False, workers=None):
    from scipy.stats import friedmanchisquare, mannwhitneyu
    os.makedirs(OUT, exist_ok=True)
    base = Params()
    if quick:
        insts, seeds, max_evals = ["eil51", "kroA100"], 5, 4000
        sens_seeds, big, big_seeds = 3, [], 0
    else:
        insts = ["eil51", "berlin52", "kroA100", "ch150", "pr299", "rat575"]
        seeds, max_evals = 30, 20000
        sens_seeds, big, big_seeds = 10, ["pr1002"], 5
    pop = 100
    tasks = [(i, a, s, max_evals, pop, base, "main")
             for i in insts for a in ALGOS for s in range(seeds)]
    tasks += [(i, a, s, max_evals, pop, base, "scale")
              for i in big for a in ("NSGA-II", "RP-MNSGA") for s in range(big_seeds)]
    sens_inst = "kroA100"
    for b in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
        tasks += [(sens_inst, "RP-MNSGA", s, max_evals, pop, replace(base, beta=b), "sens_beta")
                  for s in range(sens_seeds)]
    for R in (8.0, 10.0, 12.0, 16.0, 20.0):
        tasks += [(sens_inst, "RP-MNSGA", s, max_evals, pop, replace(base, range_km=R), "sens_range")
                  for s in range(sens_seeds)]
    for ps in (50, 200):
        tasks += [(sens_inst, "RP-MNSGA", s, max_evals, ps, base, "sens_pop")
                  for s in range(sens_seeds)]
    print(f"{len(tasks)} lần chạy, {max_evals} lần đánh giá mỗi lần")
    t0 = time.time()
    with Pool(workers or max(1, (os.cpu_count() or 2) - 4)) as pool:
        runs = []
        for k, r in enumerate(pool.imap_unordered(run_task, tasks, chunksize=1), 1):
            runs.append(r)
            if k % 50 == 0:
                print(f"  {k}/{len(tasks)}  ({time.time() - t0:.0f}s)", flush=True)

    # greedy + MILP
    greedy_res, milp_res, info = {}, {}, {}
    for name in insts + big:
        inst = get_instance(name, base)
        t1 = time.time()
        inst.evals = 0
        path = greedy(inst)
        F = np.array([s.f for s in path])
        F = F[nondominated(F)]
        greedy_res[name] = {"F": F, "hv": hypervolume(inst.normalize(F)),
                            "runtime": time.time() - t1, "evals": inst.evals,
                            "min_f3": float(F[:, 2].min())}
        info[name] = {"I": inst.I, "J": inst.J, "B": inst.B,
                      "coverable": inst.coverable}
    for name in insts[:3]:
        print("MILP", name, flush=True)
        milp_res[name] = milp_reference(get_instance(name, base))

    raw = {"runs": runs, "greedy": greedy_res, "milp": milp_res, "info": info,
           "insts": insts, "big": big, "seeds": seeds, "max_evals": max_evals,
           "sens_inst": sens_inst}
    with open(os.path.join(OUT, "raw.pkl"), "wb") as fh:
        pickle.dump(raw, fh)
    summarize(raw)
    make_plots(raw)
    print(f"Xong sau {time.time() - t0:.0f}s. Kết quả trong {OUT}")


def summarize(raw):
    from scipy.stats import friedmanchisquare, mannwhitneyu
    runs, insts = raw["runs"], raw["insts"]
    base = Params()
    main = [r for r in runs if r["tag"] == "main"]
    summary = {"config": {"seeds": raw["seeds"], "max_evals": raw["max_evals"], "pop": 100},
               "instances": raw["info"], "main": {}, "milp": raw["milp"], "greedy": {}}
    rows, mean_hv = [], {a: [] for a in ALGOS}
    for name in insts:
        inst = get_instance(name, base)
        rs = [r for r in main if r["instance"] == name]
        allF = np.vstack([inst.normalize(r["F"]) for r in rs if len(r["F"])]
                         + [inst.normalize(raw["greedy"][name]["F"])])
        ref_front = allF[nondominated(allF)]
        g = raw["greedy"][name]
        summary["greedy"][name] = {"hv": g["hv"], "min_f3": g["min_f3"],
                                   "igd": igd(inst.normalize(g["F"]), ref_front),
                                   "runtime": g["runtime"], "evals": g["evals"]}
        per = {}
        for a in ALGOS:
            ra = sorted((r for r in rs if r["algo"] == a), key=lambda r: r["seed"])
            for r in ra:
                r["igd"] = igd(inst.normalize(r["F"]), ref_front)
            per[a] = {"hv": [r["hv"] for r in ra], "igd": [r["igd"] for r in ra],
                      "rt": [r["runtime"] for r in ra], "nd": [len(r["F"]) for r in ra],
                      "f3": [r["F"][:, 2].min() if len(r["F"]) else 1.0 for r in ra]}
        others = [a for a in ALGOS if a != "RP-MNSGA"]
        pv = [mannwhitneyu(per["RP-MNSGA"]["hv"], per[a]["hv"], alternative="two-sided").pvalue
              for a in others]
        padj = dict(zip(others, holm(np.array(pv))))
        summary["main"][name] = {}
        for a in ALGOS:
            d = per[a]
            sign = ""
            if a != "RP-MNSGA":
                better = np.mean(per["RP-MNSGA"]["hv"]) > np.mean(d["hv"])
                sign = "=" if padj[a] >= 0.05 else ("+" if better else "-")
            rec = {"hv_mean": float(np.mean(d["hv"])), "hv_std": float(np.std(d["hv"])),
                   "igd_mean": float(np.mean(d["igd"])), "igd_std": float(np.std(d["igd"])),
                   "runtime_mean": float(np.mean(d["rt"])), "nd_mean": float(np.mean(d["nd"])),
                   "min_f3_mean": float(np.mean(d["f3"])), "min_f3_best": float(np.min(d["f3"])),
                   "p_holm": None if a == "RP-MNSGA" else float(padj[a]), "sign": sign}
            summary["main"][name][a] = rec
            mean_hv[a].append(rec["hv_mean"])
            rows.append([name, a, f"{rec['hv_mean']:.4f}", f"{rec['hv_std']:.4f}",
                         f"{rec['igd_mean']:.4f}", f"{rec['igd_std']:.4f}",
                         f"{rec['min_f3_mean']:.4f}", f"{rec['nd_mean']:.1f}",
                         f"{rec['runtime_mean']:.2f}",
                         "" if rec["p_holm"] is None else f"{rec['p_holm']:.2e}", sign])
        # gap so với MILP
        if name in raw["milp"]:
            m = raw["milp"][name]
            gaps = {}
            for a in ("NSGA-II", "RP-MNSGA"):
                ra = [r for r in rs if r["algo"] == a]
                gp = {"f3": float(np.mean([r["F"][:, 2].min() - m["f3_star"] for r in ra]))}
                for pt in m["points"]:
                    vals = []
                    for r in ra:
                        ok = r["F"][r["F"][:, 2] <= pt["eps"] + 1e-9]
                        if len(ok):
                            vals.append((ok[:, 1].min() - pt["f2"]) / pt["f2"] * 100)
                    gp[f"f2@{pt['eps']}"] = {"gap_pct": float(np.mean(vals)) if vals else None,
                                             "reached": len(vals)}
                gaps[a] = gp
            gF = raw["greedy"][name]["F"]
            gp = {"f3": float(gF[:, 2].min() - m["f3_star"])}
            for pt in m["points"]:
                ok = gF[gF[:, 2] <= pt["eps"] + 1e-9]
                gp[f"f2@{pt['eps']}"] = {"gap_pct": float((ok[:, 1].min() - pt["f2"]) / pt["f2"] * 100)
                                         if len(ok) else None, "reached": int(len(ok) > 0)}
            gaps["Greedy"] = gp
            summary["milp"][name]["gaps"] = gaps
    with open(os.path.join(OUT, "table_main.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["instance", "algorithm", "HV_mean", "HV_std", "IGD_mean", "IGD_std",
                     "min_f3_mean", "ND_mean", "runtime_s", "p_holm_vs_RP-MNSGA", "sign"])
        wr.writerows(rows)
    # Friedman trên HV trung bình theo instance
    M = np.array([mean_hv[a] for a in ALGOS]).T          # (instance, algo)
    ranks = np.array([(-row).argsort().argsort() + 1 for row in M]).mean(0)
    fr = friedmanchisquare(*[M[:, k] for k in range(M.shape[1])]) if len(insts) >= 3 else None
    summary["friedman"] = {"avg_rank": dict(zip(ALGOS, map(float, ranks))),
                           "stat": None if fr is None else float(fr.statistic),
                           "p": None if fr is None else float(fr.pvalue)}
    # độ nhạy
    sens = {}
    for tag, key in (("sens_beta", "beta"), ("sens_range", "range_km"), ("sens_pop", "pop")):
        rs = [r for r in runs if r["tag"] == tag]
        if tag == "sens_pop":
            rs += [dict(r, tag=tag) for r in main
                   if r["instance"] == raw["sens_inst"] and r["algo"] == "RP-MNSGA"]
        out = []
        for v in sorted({r[key] for r in rs}):
            rv = [r for r in rs if r[key] == v and r["best_cov"]]
            p = replace(base, **({key: v} if key != "pop" else {}))
            inst = get_instance(raw["sens_inst"], p)
            out.append({key: v, "B": inst.B, "coverable": inst.coverable, "runs": len(rv),
                        "min_f3": float(np.mean([r["best_cov"]["f"][2] for r in rv])),
                        "f1_at_min_f3": float(np.mean([r["best_cov"]["f"][0] for r in rv])),
                        "stations": float(np.mean([sum(1 for x in r["best_cov"]["n"] if x) for r in rv])),
                        "uavs": float(np.mean([sum(r["best_cov"]["n"]) for r in rv])),
                        "hv": float(np.mean([r["hv"] for r in rv])),
                        "hv_std": float(np.std([r["hv"] for r in rv]))})
        sens[tag] = out
    summary["sensitivity"] = sens
    # khả năng mở rộng
    sc = []
    for name in insts + raw["big"]:
        for a in ("NSGA-II", "RP-MNSGA"):
            ra = [r for r in runs if r["instance"] == name and r["algo"] == a
                  and r["tag"] in ("main", "scale")]
            if ra:
                sc.append({"instance": name, "I": raw["info"][name]["I"], "J": raw["info"][name]["J"],
                           "algo": a, "runtime": float(np.mean([r["runtime"] for r in ra])),
                           "hv": float(np.mean([r["hv"] for r in ra])),
                           "hv_std": float(np.std([r["hv"] for r in ra])), "runs": len(ra)})
    summary["scalability"] = sc
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, ensure_ascii=False)
    return summary


# ----------------------------------------------------------------------------
# 6. Hình vẽ
# ----------------------------------------------------------------------------
COL = {"NSGA-II": "#2a78d6", "RP-MNSGA": "#eb6834", "w/o repair": "#1baf7a",
       "w/o LS": "#eda100", "w/o seeding": "#e87ba4", "Greedy": "#1baf7a"}
INK, INK2, MUTED, GRID, AXIS, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"


def _style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 11,
        "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "text.color": INK,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2,
        "ytick.labelcolor": INK2, "axes.grid": True, "grid.color": GRID,
        "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "legend.frameon": False, "lines.linewidth": 2, "axes.axisbelow": True})
    return plt


def make_plots(raw=None):
    if raw is None:
        with open(os.path.join(OUT, "raw.pkl"), "rb") as fh:
            raw = pickle.load(fh)
    plt = _style()
    base = Params()
    runs, insts = raw["runs"], raw["insts"]
    main = [r for r in runs if r["tag"] == "main"]
    with open(os.path.join(OUT, "summary.json"), encoding="utf-8") as fh:
        summary = json.load(fh)
    show = raw["sens_inst"] if raw["sens_inst"] in insts else insts[0]

    # Hình 1: mặt Pareto (2 hình chiếu), seed 0
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    series = [("NSGA-II", [r for r in main if r["instance"] == show and r["algo"] == "NSGA-II"
                           and r["seed"] == 0][0]["F"], "o"),
              ("RP-MNSGA", [r for r in main if r["instance"] == show and r["algo"] == "RP-MNSGA"
                            and r["seed"] == 0][0]["F"], "s"),
              ("Greedy", raw["greedy"][show]["F"], "^")]
    for ax, (col, lab) in zip(axes, ((0, "f1: thời gian phản ứng TB (phút)"),
                                     (1, "f2: năng lượng (kWh)"))):
        for name, F, mk in series:
            y = F[:, col] / (1000 if col == 1 else 1)
            ax.scatter(F[:, 2] * 100, y, s=34, marker=mk, color=COL[name], label=name,
                       edgecolors=SURF, linewidths=0.8, zorder=3)
        if col == 1 and show in raw["milp"]:
            m = raw["milp"][show]
            ax.scatter([p["f3"] * 100 for p in m["points"]], [p["f2"] / 1000 for p in m["points"]],
                       s=70, marker="D", color=INK, label="MILP (tối ưu)", zorder=4,
                       edgecolors=SURF, linewidths=0.8)
        ax.set_xlabel("f3: rủi ro không được phủ (%)")
        ax.set_ylabel(lab)
    axes[0].set_title(f"{show}: đánh đổi độ phủ và thời gian phản ứng")
    axes[1].set_title(f"{show}: đánh đổi độ phủ và năng lượng")
    axes[1].legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig1_pareto.png"), dpi=170)
    plt.close(fig)

    # Hình 2: hội tụ HV
    pick = [i for i in (insts[0], show, insts[-1])]
    pick = list(dict.fromkeys(pick))
    fig, axes = plt.subplots(1, len(pick), figsize=(4.6 * len(pick), 4.2), squeeze=False)
    for ax, name in zip(axes[0], pick):
        for a in ALGOS:
            H = np.array([[h[1] for h in r["hist"]] for r in main
                          if r["instance"] == name and r["algo"] == a and len(r["hist"]) == 20])
            if len(H) == 0:
                continue
            x = np.array([h[0] for h in [r for r in main if r["instance"] == name
                                         and r["algo"] == a][0]["hist"]]) / 1000
            ax.plot(x, H.mean(0), color=COL[a], label=a,
                    linestyle="-" if a in ("NSGA-II", "RP-MNSGA") else "--")
        ax.set_title(name)
        ax.set_xlabel("Số lần đánh giá (nghìn)")
        ax.set_ylabel("Hypervolume trung bình")
    axes[0][-1].legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig2_convergence.png"), dpi=170)
    plt.close(fig)

    # Hình 3: độ nhạy theo ngân sách và tầm bay
    sb, sr = summary["sensitivity"]["sens_beta"], summary["sensitivity"]["sens_range"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, data, key, xl in ((axes[0], sb, "B", "Ngân sách B"),
                              (axes[1], sr, "range_km", "Tầm bay khứ hồi R (km)")):
        x = [d[key] for d in data]
        y = [d["min_f3"] * 100 for d in data]
        ax.plot(x, y, color=COL["RP-MNSGA"], marker="o", markersize=7,
                label="RP-MNSGA: f3 nhỏ nhất đạt được")
        ax.plot(x, [(1 - d["coverable"]) * 100 for d in data], color=MUTED, linestyle=":",
                label="Cận dưới (ngoài tầm mọi ứng viên)")
        for xi, yi in zip(x, y):
            ax.annotate(f"{yi:.1f}", (xi, yi), textcoords="offset points", xytext=(0, 9),
                        ha="center", fontsize=9, color=INK2)
        ax.set_xlabel(xl)
        ax.set_ylabel("Rủi ro không được phủ (%)")
        ax.set_ylim(bottom=0)
        ax.legend(loc="upper right", fontsize=9)
    axes[0].set_title(f"{raw['sens_inst']}: lợi ích biên giảm dần theo ngân sách")
    axes[1].set_title(f"{raw['sens_inst']}: ảnh hưởng của dung lượng pin")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig3_sensitivity.png"), dpi=170)
    plt.close(fig)

    # Hình 4: bản đồ lời giải phủ tốt nhất
    inst = get_instance(show, base)
    cands = [r for r in main if r["instance"] == show and r["algo"] == "RP-MNSGA" and r["best_cov"]]
    best = min(cands, key=lambda r: tuple(r["best_cov"]["f"][2::-2]))["best_cov"]
    n, assign = np.array(best["n"]), np.array(best["assign"])
    span = inst.xy.max(0)
    fig, ax = plt.subplots(figsize=(10, 10 * span[1] / span[0] + 1.9))
    ax.grid(False)
    cov = assign >= 0
    for i in np.where(cov)[0]:
        c = inst.xy[inst.cand[assign[i]]]
        ax.plot([inst.xy[i, 0], c[0]], [inst.xy[i, 1], c[1]], color="#9ec5f4", lw=0.8, zorder=1)
    ax.scatter(inst.xy[cov, 0], inst.xy[cov, 1], s=8 + 9 * inst.w[cov], color="#2a78d6",
               edgecolors=SURF, linewidths=0.6, zorder=2, label="Điểm được phủ")
    ax.scatter(inst.xy[~cov, 0], inst.xy[~cov, 1], s=8 + 9 * inst.w[~cov], color="#c3c2b7",
               edgecolors=SURF, linewidths=0.6, zorder=2, label="Điểm chưa phủ")
    closed = inst.cand[n == 0]
    ax.scatter(inst.xy[closed, 0], inst.xy[closed, 1], s=60, marker="x", color=MUTED,
               linewidths=1.2, zorder=3, label="Ứng viên không mở")
    op = np.where(n > 0)[0]
    ax.scatter(inst.xy[inst.cand[op], 0], inst.xy[inst.cand[op], 1], s=230, marker="s",
               color="#eb6834", edgecolors=SURF, linewidths=1.2, zorder=4,
               label="Trạm sạc (số = UAV)")
    for j in op:
        x, y = inst.xy[inst.cand[j]]
        ax.text(x, y, str(n[j]), ha="center", va="center", color="white",
                fontsize=10, fontweight="bold", zorder=5)
    ax.set_aspect("equal")
    ax.set_xlabel("km")
    ax.set_ylabel("km")
    ax.set_title(f"{show}: {len(op)} trạm, {int(n.sum())} UAV, phủ "
                 f"{(1 - best['f'][2]) * 100:.1f}% rủi ro (cỡ điểm = mức rủi ro)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=4, fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig4_map.png"), dpi=170, bbox_inches="tight")
    plt.close(fig)

    # Hình 5: thời gian chạy theo quy mô
    sc = summary["scalability"]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    for a in ("NSGA-II", "RP-MNSGA"):
        d = sorted((s for s in sc if s["algo"] == a), key=lambda s: s["I"])
        ax.plot([s["I"] for s in d], [s["runtime"] for s in d], color=COL[a], marker="o",
                markersize=7, label=a)
        ax.annotate(a, (d[-1]["I"], d[-1]["runtime"]), textcoords="offset points",
                    xytext=(-8, 8), ha="right", color=INK2, fontsize=10)
    ax.set_xlabel("Số điểm nhu cầu |I|")
    ax.set_ylabel("Thời gian chạy trung bình (giây)")
    ax.set_title(f"Thời gian cho {raw['max_evals']:,} lần đánh giá".replace(",", "."))
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig5_scalability.png"), dpi=170)
    plt.close(fig)


def demo():
    inst = Instance("kroA100")
    print(f"kroA100: |I|={inst.I}, |J|={inst.J}, B={inst.B}, "
          f"rủi ro có thể phủ tối đa={inst.coverable:.1%}")
    path = greedy(inst)
    F = np.array([s.f for s in path])
    print(f"Greedy   : HV={hypervolume(inst.normalize(F[nondominated(F)])):.4f}  "
          f"min f3={F[:, 2].min():.3f}  ({inst.evals} lần đánh giá)")
    for a in ("NSGA-II", "RP-MNSGA"):
        r = MOEA(inst, ALGOS[a], seed=0, max_evals=10000).run()
        print(f"{a:9s}: HV={r['hv']:.4f}  min f3={r['F'][:, 2].min():.3f}  "
              f"|front|={len(r['F'])}  {r['runtime']:.1f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("cmd", choices=["demo", "experiment", "plots"])
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()
    if args.cmd == "demo":
        demo()
    elif args.cmd == "experiment":
        experiment(args.quick, args.workers)
    else:
        make_plots()
