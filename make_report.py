#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sinh báo cáo Word (BaoCao_Nhom8_UAV.docx) từ results/summary.json và các hình.
Chạy sau `python uav_station_fleet.py experiment`."""
import json
import os

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "results")
S = json.load(open(os.path.join(OUT, "summary.json"), encoding="utf-8"))
INSTS = list(S["main"].keys())
ALGOS = ["NSGA-II", "w/o repair", "w/o LS", "w/o seeding", "RP-MNSGA"]
FONT = "Times New Roman"

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.left_margin, sec.right_margin = Cm(3), Cm(2)
sec.top_margin = sec.bottom_margin = Cm(2.5)


def _font(style, size, bold=False, color=None):
    style.font.name = FONT
    style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = RGBColor(*(color or (0, 0, 0)))


_font(doc.styles["Normal"], 13)
doc.styles["Normal"].paragraph_format.space_after = Pt(6)
doc.styles["Normal"].paragraph_format.line_spacing = 1.3
for name, size in (("Heading 1", 15), ("Heading 2", 13.5)):
    st = doc.styles[name]
    _font(st, size, bold=True, color=(0x14, 0x21, 0x3D))
    st.paragraph_format.space_before = Pt(14)
    st.paragraph_format.space_after = Pt(6)
    st.paragraph_format.keep_with_next = True
for name in ("List Bullet", "List Number"):
    _font(doc.styles[name], 13)

_counter = {"tab": 0, "fig": 0}


def para(text, align=WD_ALIGN_PARAGRAPH.JUSTIFY, size=None, italic=False, bold=False,
         indent=True, after=None):
    """Đoạn văn; **...** trong text thành chữ đậm."""
    p = doc.add_paragraph()
    p.alignment = align
    if indent and align == WD_ALIGN_PARAGRAPH.JUSTIFY:
        p.paragraph_format.first_line_indent = Cm(0.8)
    if after is not None:
        p.paragraph_format.space_after = Pt(after)
    for k, part in enumerate(text.split("**")):
        if not part:
            continue
        r = p.add_run(part)
        r.bold = bold or k % 2 == 1
        r.italic = italic
        if size:
            r.font.size = Pt(size)
    return p


def bullets(items, style="List Bullet"):
    for it in items:
        p = doc.add_paragraph(style=style)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(3)
        for k, part in enumerate(it.split("**")):
            if part:
                p.add_run(part).bold = k % 2 == 1


def formula(lines):
    for ln in lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.left_indent = Cm(1.5)
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(ln)
        r.font.name = "Cambria Math"
        r.font.size = Pt(12)
    doc.paragraphs[-1].paragraph_format.space_after = Pt(8)


def _shade(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hexcolor)
    tcPr.append(shd)


def table(caption, header, rows, widths, size=10.5, bold_col=None, align_left=(0,)):
    _counter["tab"] += 1
    c = para(f"**Bảng {_counter['tab']}.** {caption}", align=WD_ALIGN_PARAGRAPH.LEFT,
             size=12, after=3)
    c.paragraph_format.keep_with_next = True
    c.paragraph_format.space_before = Pt(8)
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for row in [header] + rows:
        cells = t.rows[0].cells if row is header else t.add_row().cells
        for k, (cell, val) in enumerate(zip(cells, row)):
            cell.width = Cm(widths[k])
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.line_spacing = 1.0
            p.alignment = (WD_ALIGN_PARAGRAPH.LEFT if k in align_left
                           else WD_ALIGN_PARAGRAPH.CENTER)
            r = p.add_run(str(val))
            r.font.size = Pt(size)
            r.bold = row is header or k == bold_col
            if row is header:
                _shade(cell, "DCE3EE")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def figure(fname, caption, width_cm=16):
    _counter["fig"] += 1
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_after = Pt(2)
    p.add_run().add_picture(os.path.join(OUT, fname), width=Cm(width_cm))
    para(f"**Hình {_counter['fig']}.** {caption}", align=WD_ALIGN_PARAGRAPH.CENTER,
         size=12, after=10)


def vn(x, nd=4):
    """Số thập phân kiểu Việt Nam (dấu phẩy)."""
    return f"{x:.{nd}f}".replace(".", ",")


H1 = lambda t: doc.add_heading(t, level=1)
H2 = lambda t: doc.add_heading(t, level=2)
main = S["main"]
cfg = S["config"]

# ============================================================================
# Trang đầu
# ============================================================================
para("BÁO CÁO BÀI TẬP NGHIÊN CỨU MÔN HỌC", align=WD_ALIGN_PARAGRAPH.CENTER, size=13, after=4)
para("UAV CHARGING-STATION PLACEMENT VÀ FLEET SIZING", align=WD_ALIGN_PARAGRAPH.CENTER,
     size=18, bold=True, after=4)
para("Tối ưu đa mục tiêu vị trí trạm sạc, quy mô đội bay và vùng phục vụ bằng "
     "NSGA-II lai có cơ chế sửa lời giải ưu tiên rủi ro",
     align=WD_ALIGN_PARAGRAPH.CENTER, size=13, italic=True, after=10)
para("Nhóm 8: [Họ tên các thành viên]", align=WD_ALIGN_PARAGRAPH.CENTER, size=13, after=2)
para("Giảng viên hướng dẫn: [Họ tên giảng viên]", align=WD_ALIGN_PARAGRAPH.CENTER,
     size=13, after=14)

# ============================================================================
# Tóm tắt (điền sau khi có số liệu: xem ABSTRACT ở cuối file)
# ============================================================================
H1("Tóm tắt")
ABSTRACT_ANCHOR = doc.add_paragraph()

# ============================================================================
# 1. Giới thiệu
# ============================================================================
H1("1. Giới thiệu vấn đề nghiên cứu")
para("Máy bay không người lái (UAV) ngày càng được dùng để giám sát, cảnh báo sớm và "
     "tiếp tế trong ứng phó thiên tai. Hạn chế lớn nhất của UAV cỡ nhỏ là pin: thời "
     "gian bay chỉ vào khoảng vài chục phút, nên vùng mà một UAV với tới được phụ thuộc "
     "hoàn toàn vào vị trí trạm sạc nơi nó xuất phát và quay về. Vì vậy, bố trí trạm sạc "
     "là quyết định hạ tầng ở mức chiến lược: nếu trạm đặt sai chỗ hoặc thiếu máy bay, "
     "thuật toán định tuyến ở tầng dưới dù tốt đến đâu cũng không bù được thời gian "
     "phản ứng.")
para("Bài toán gồm ba quyết định gắn chặt với nhau: (i) mở trạm sạc ở những vị trí ứng "
     "viên nào, (ii) bố trí bao nhiêu UAV tại mỗi trạm (fleet sizing), và (iii) mỗi trạm "
     "phục vụ những điểm nhu cầu nào. Ba mục tiêu cần đạt lại mâu thuẫn nhau khi ngân "
     "sách có hạn: phản ứng nhanh và phủ được nhiều rủi ro đòi hỏi nhiều trạm, nhiều "
     "UAV, trong khi chi phí và năng lượng bay lại muốn ít. Do đó bài toán được đặt dưới "
     "dạng tối ưu đa mục tiêu, và lời giải là một tập phương án đánh đổi (mặt Pareto) "
     "thay vì một phương án duy nhất.")
para("Báo cáo trả lời ba câu hỏi nghiên cứu:")
bullets([
    "**RQ1.** Với ngân sách cho trước, cấu hình trạm và đội bay nào cho mặt Pareto tốt "
    "nhất giữa thời gian phản ứng, năng lượng và rủi ro không được phủ?",
    "**RQ2.** Cơ chế sửa lời giải ưu tiên rủi ro (risk-priority repair), tìm kiếm cục bộ "
    "và khởi tạo từ greedy có cải thiện NSGA-II chuẩn một cách có ý nghĩa thống kê không?",
    "**RQ3.** Lời giải thay đổi thế nào theo ngân sách, dung lượng pin và quy mô bài toán?",
])
para("Đóng góp của báo cáo gồm: (1) một mô hình đa mục tiêu tích hợp đặt trạm, xác định "
     "quy mô đội bay và gán vùng phục vụ, có trọng số rủi ro; (2) thuật toán RP-MNSGA, "
     "một biến thể NSGA-II lai (memetic) với mã hóa rút gọn, bộ giải mã ưu tiên rủi ro, "
     "cơ chế repair và tìm kiếm cục bộ; (3) bộ thực nghiệm tái lập được trên TSPLIB với "
     "30 seed, phân tích ablation, độ nhạy, khả năng mở rộng và kiểm định thống kê.")

# ============================================================================
# 2. Nghiên cứu liên quan
# ============================================================================
H1("2. Các nghiên cứu liên quan")
H2("2.1. Bài toán định vị cơ sở kinh điển")
para("Bài toán p-median [1] chọn p cơ sở để cực tiểu tổng khoảng cách có trọng số. Bài "
     "toán phủ tập hợp vị trí (LSCP) [2] tìm số cơ sở ít nhất để phủ mọi điểm nhu cầu "
     "trong một bán kính, còn bài toán phủ cực đại (MCLP) [3] tối đa hóa nhu cầu được "
     "phủ với số cơ sở cho trước. Daskin [4] mở rộng MCLP sang trường hợp cơ sở có thể "
     "bận (MEXCLP), rất gần với bối cảnh dịch vụ khẩn cấp. Hàm phủ có tính submodular, "
     "nên thuật toán tham lam đạt tỉ lệ xấp xỉ 1 − 1/e cho mục tiêu phủ không có ràng "
     "buộc năng lực [14]; heuristic hoán đổi của Teitz và Bart [13] là nền tảng của "
     "nhiều phép tìm kiếm cục bộ cho bài toán định vị.")
H2("2.2. Đặt trạm sạc và trạm xuất phát cho drone")
para("Hong và cộng sự [5] đề xuất mô hình phủ có giới hạn tầm bay để đặt trạm sạc cho "
     "dịch vụ giao hàng bằng drone. Chauhan và cộng sự [6] xét bài toán phủ cực đại có "
     "năng lực với drone bị giới hạn tầm hoạt động. Trong y tế khẩn cấp, Boutilier và "
     "cộng sự [7] tối ưu mạng drone chở máy khử rung tim, xác định đồng thời vị trí trạm "
     "và số drone cần thiết để đạt thời gian đáp ứng mục tiêu.")
H2("2.3. Quy mô đội bay và UAV trong tình huống khẩn cấp")
para("Ghelichi và cộng sự [8] nghiên cứu hậu cần cho đội drone chở vật tư y tế, trong đó "
     "vị trí trạm sạc và lịch bay được quyết định cùng nhau. Bài báo tham khảo của đề "
     "tài, Wang và cộng sự [9], tối ưu quỹ đạo nhiều pha và phối hợp UAV với xe mặt đất "
     "trong giao hàng khẩn cấp; công trình này tập trung vào tầng vận hành, còn báo cáo "
     "này xét tầng hạ tầng đứng trước nó.")
H2("2.4. Thuật toán tiến hóa đa mục tiêu")
para("NSGA-II [10] là thuật toán tiến hóa đa mục tiêu phổ biến nhất, dựa trên sắp xếp "
     "không trội và khoảng cách chen chúc. MOEA/D [11] phân rã bài toán thành các bài "
     "toán con vô hướng, còn NSGA-III [12] dùng điểm tham chiếu cho bài toán nhiều mục "
     "tiêu. Với bài toán tổ hợp có ràng buộc, các biến thể lai kết hợp tìm kiếm cục bộ "
     "và toán tử sửa lời giải thường hiệu quả hơn thuật toán thuần túy. Chất lượng tập "
     "nghiệm thường được đo bằng hypervolume [16] và IGD.")
H2("2.5. Khoảng trống nghiên cứu")
bullets([
    "Đa số mô hình đặt trạm cho drone tối ưu một mục tiêu (độ phủ hoặc chi phí).",
    "Quy mô đội bay thường được quyết định tách rời hoặc sau khi đã cố định vị trí trạm.",
    "Ít công trình đưa trọng số rủi ro của từng điểm nhu cầu vào cả mục tiêu lẫn toán "
    "tử tìm kiếm.",
    "Ít công trình báo cáo ablation và kiểm định thống kê trên benchmark công khai.",
])

# ============================================================================
# 3. Bài toán
# ============================================================================
H1("3. Bài toán nghiên cứu")
H2("3.1. Dữ liệu vào và biến quyết định")
para("Cho tập điểm nhu cầu I, mỗi điểm i có tọa độ, trọng số rủi ro w_i và số nhiệm vụ "
     "λ_i trong một chu kỳ hoạt động T. Cho tập vị trí ứng viên J; mở một trạm tốn chi "
     "phí c_s và mỗi trạm chứa tối đa U_max UAV. Mỗi UAV có chi phí c_u, tốc độ v, tầm "
     "bay khứ hồi R, tiêu thụ e (Wh/km) và cần thời gian sạc τ sau mỗi nhiệm vụ. Ngân "
     "sách tổng là B; d_ij là khoảng cách Euclid giữa điểm i và ứng viên j.")
bullets([
    "y_j ∈ {0, 1}: bằng 1 nếu mở trạm tại ứng viên j.",
    "n_j ∈ {0, 1, …, U_max}: số UAV bố trí tại trạm j.",
    "x_ij ∈ {0, 1}: bằng 1 nếu điểm i được trạm j phục vụ.",
])
H2("3.2. Hàm mục tiêu")
para("Ba mục tiêu cùng được cực tiểu hóa:")
formula([
    "f1 = Σ_i Σ_j w_i · (d_ij / v) · x_ij  /  Σ_i Σ_j w_i · x_ij",
    "f2 = Σ_i Σ_j λ_i · 2e · d_ij · x_ij",
    "f3 = 1 − ( Σ_i Σ_j w_i · x_ij ) / Σ_i w_i",
])
para("f1 là thời gian phản ứng trung bình có trọng số rủi ro của các điểm được phủ, f2 "
     "là tổng năng lượng bay trong một chu kỳ, f3 là tỉ lệ rủi ro không được phủ. f1 "
     "được lấy trung bình trên phần được phủ để tách khỏi f2 (vốn tỉ lệ với tổng quãng "
     "đường); phần chưa phủ đã được phản ánh qua f3.")
H2("3.3. Ràng buộc")
formula([
    "Σ_j x_ij ≤ 1,  ∀i                                   (mỗi điểm thuộc tối đa một trạm)",
    "2 · d_ij · x_ij ≤ R,  ∀i, j                         (tầm bay của pin)",
    "Σ_i λ_i · (2·d_ij / v + τ) · x_ij ≤ n_j · T,  ∀j    (năng lực đội bay tại trạm)",
    "n_j ≤ U_max · y_j,  ∀j                              (sức chứa trạm)",
    "c_s · Σ_j y_j + c_u · Σ_j n_j ≤ B                   (ngân sách)",
])
H2("3.4. Độ phức tạp")
para("Khi bỏ ràng buộc năng lực và chỉ giữ mục tiêu f3, bài toán trở thành MCLP, vốn "
     "NP-hard; do đó bài toán đang xét cũng NP-hard. Riêng vector số UAV đã có "
     "(U_max + 1)^|J| cấu hình, chưa kể phép gán x_ij. Mô hình MILP chỉ giải được tới "
     "tối ưu trên instance nhỏ, vì vậy báo cáo dùng MILP làm nghiệm tham chiếu và dùng "
     "metaheuristic cho các instance lớn hơn.")

# ============================================================================
# 4. Hướng tiếp cận
# ============================================================================
H1("4. Hướng tiếp cận và đề xuất")
H2("4.1. Các thuật toán baseline (Pha 1)")
bullets([
    "**Greedy kiểu MCLP có xét năng lực.** Bắt đầu từ cấu hình rỗng; mỗi bước thêm một "
    "UAV vào trạm đang mở hoặc mở một trạm mới với một UAV, chọn phương án có rủi ro phủ "
    "thêm (ước lượng theo năng lực mới) trên chi phí lớn nhất, cho tới khi hết ngân "
    "sách. Các bước trung gian tạo thành một tập lời giải ở các mức ngân sách khác nhau.",
    "**MILP.** Mô hình ở Mục 3 được giải bằng HiGHS (qua scipy) trên ba instance nhỏ "
    "nhất: trước hết cực tiểu f3 dưới ràng buộc ngân sách để có f3*, sau đó cực tiểu f2 "
    "với f3 ≤ f3* + δ (phương pháp ε-constraint) tại δ = 0,05; 0,15; 0,30.",
    "**NSGA-II chuẩn.** Dùng cùng mã hóa và bộ giải mã với thuật toán đề xuất, khởi tạo "
    "ngẫu nhiên, lai đồng nhất, đột biến từng gen, xử lý ràng buộc ngân sách bằng "
    "constraint-domination; không có repair và tìm kiếm cục bộ.",
])
H2("4.2. Thuật toán đề xuất RP-MNSGA (Pha 2)")
para("Hướng mở rộng được chọn cho Pha 2 là **đa mục tiêu kết hợp constraint repair**. "
     "RP-MNSGA (Risk-Priority Memetic NSGA-II) giữ khung NSGA-II và bổ sung năm thành phần:")
bullets([
    "**Mã hóa rút gọn.** Mỗi trạm ứng viên j có hai gen: số UAV n_j (n_j = 0 nghĩa là "
    "không mở trạm) và mức bán kính phục vụ q_j ∈ {1, …, 4}, ứng với bán kính "
    "q_j/4 · R/2. Thuật toán tiến hóa không phải tìm trực tiếp trên các biến x_ij.",
    "**Bộ giải mã ưu tiên rủi ro.** Duyệt các điểm nhu cầu theo w_i giảm dần; mỗi điểm "
    "được gán vào trạm gần nhất đang mở, có bán kính phục vụ chứa điểm đó và còn đủ "
    "năng lực. Lời giải sau giải mã luôn thỏa ràng buộc pin, năng lực và sức chứa.",
    "**Risk-priority repair.** (a) Loại các UAV nhàn rỗi, việc này không đổi mục tiêu "
    "nhưng giải phóng ngân sách. (b) Nếu vượt ngân sách, lần lượt bớt UAV hoặc đóng trạm "
    "có tỉ số rủi ro đang phủ trên chi phí thấp nhất. (c) Nếu còn dư ngân sách, với xác "
    "suất 0,5 thêm một UAV hoặc trạm tại nơi có lợi ích biên lớn nhất.",
    "**Tìm kiếm cục bộ.** Mỗi thế hệ chọn 5 cá thể ở front đầu, mỗi cá thể thử 3 lân "
    "cận từ năm phép biến đổi: dời một trạm yếu sang vị trí lân cận, chuyển một UAV giữa "
    "hai trạm, đóng trạm đóng góp thấp, co giãn bán kính phục vụ, thêm UAV theo lợi ích "
    "biên. Lân cận được nhận nếu cải thiện một hàm vô hướng hóa với trọng số ngẫu nhiên.",
    "**Khởi tạo lai.** 20% quần thể ban đầu lấy từ các bước của greedy, phần còn lại "
    "sinh ngẫu nhiên.",
])
H2("4.3. Phân tích độ phức tạp")
para("Tiền xử lý danh sách các trạm trong tầm bay của từng điểm tốn O(|I|·|J|·log|J|). "
     "Mỗi lần giải mã tốn O(|I|·k), với k là số trạm trung bình trong tầm bay của một "
     "điểm. Mỗi thế hệ NSGA-II tốn O(M·N²) cho sắp xếp không trội (M = 3 mục tiêu, N là "
     "kích thước quần thể) cộng N lần giải mã. Một lần repair tốn thêm tối đa một lần "
     "giải mã và một lần tính lợi ích biên O(|I|·k). Mọi lần giải mã, kể cả trong repair, "
     "tìm kiếm cục bộ và khởi tạo greedy, đều được tính vào ngân sách đánh giá để so "
     "sánh công bằng.")

# ============================================================================
# 5. Thiết kế thử nghiệm
# ============================================================================
H1("5. Thiết kế thử nghiệm và đánh giá")
H2("5.1. Dữ liệu")
para("Thực nghiệm dùng tọa độ của các instance TSPLIB [15] làm điểm nhu cầu. Tọa độ được "
     "tịnh tiến và co giãn sao cho cạnh dài của vùng nghiên cứu bằng 30 km. Tập ứng viên "
     "gồm |J| = min(max(15, |I|/4), 120) nút chọn ngẫu nhiên. Trọng số rủi ro w_i ∈ [1, 10] "
     "được sinh từ ba điểm nóng dạng Gauss (độ lệch chuẩn 5,4 km), số nhiệm vụ λ_i là số "
     "nguyên ngẫu nhiên từ 1 đến 5. Mọi yếu tố ngẫu nhiên của instance dùng seed cố định "
     "2026 nên bộ dữ liệu tái lập được hoàn toàn. Ngân sách đặt bằng B = β·(c_s·|J| + "
     "c_u·U_cần), với U_cần là số UAV ước lượng để phục vụ toàn bộ nhu cầu và β = 0,3.")
info = S["instances"]
table("Các instance thực nghiệm (β = 0,3; R = 12 km).",
      ["Instance", "Số điểm |I|", "Số ứng viên |J|", "Ngân sách B", "Rủi ro phủ được tối đa"],
      [[k, v["I"], v["J"], int(v["B"]), vn(v["coverable"] * 100, 1) + "%"]
       for k, v in info.items()],
      [3.2, 2.8, 3.0, 2.8, 4.2])
para("Cột cuối là tỉ lệ rủi ro nằm trong tầm bay của ít nhất một vị trí ứng viên, tức "
     "cận trên của độ phủ khi ngân sách không giới hạn. Instance pr1002 chỉ dùng cho thí "
     "nghiệm mở rộng quy mô.")
table("Tham số của mô hình.",
      ["Tham số", "Giá trị", "Tham số", "Giá trị"],
      [["Tốc độ v", "60 km/h", "Chi phí trạm c_s", "10"],
       ["Tầm bay khứ hồi R", "12 km", "Chi phí UAV c_u", "2"],
       ["Tiêu thụ e", "25 Wh/km", "Sức chứa U_max", "6 UAV"],
       ["Thời gian sạc τ", "0,5 giờ", "Chu kỳ T", "8 giờ"]],
      [4.2, 3.2, 4.2, 3.2], align_left=(0, 2))
H2("5.2. Thuật toán và tham số")
para(f"So sánh Greedy, MILP (trên eil51, berlin52, kroA100), NSGA-II chuẩn, RP-MNSGA và "
     f"ba biến thể ablation của RP-MNSGA: bỏ repair (w/o repair), bỏ tìm kiếm cục bộ "
     f"(w/o LS), bỏ khởi tạo greedy (w/o seeding). Mọi thuật toán tiến hóa dùng quần thể "
     f"{cfg['pop']}, xác suất lai 0,9, xác suất đột biến 1/|J| cho mỗi gen và dừng sau "
     f"{cfg['max_evals'] // 1000}.000 lần đánh giá (giải mã). Mỗi cấu hình chạy "
     f"{cfg['seeds']} seed độc lập.")
H2("5.3. Chỉ số đánh giá và kiểm định")
bullets([
    "**Hypervolume (HV).** Tính chính xác trong không gian ba mục tiêu đã chuẩn hóa "
    "(f1 chia cho thời gian bay tới biên tầm bay, f2 chia cho năng lượng khi mọi điểm ở "
    "biên tầm bay, f3 giữ nguyên) với điểm tham chiếu (1,1; 1,1; 1,1). HV càng lớn càng tốt.",
    "**IGD.** Khoảng cách trung bình từ mặt tham chiếu (tập không trội của hợp mọi lời "
    "giải tìm được trên instance đó) tới tập nghiệm của thuật toán. IGD càng nhỏ càng tốt.",
    "**Khoảng cách tới MILP.** Chênh lệch f3 nhỏ nhất so với f3*, và chênh lệch tương "
    "đối của f2 nhỏ nhất trong các lời giải đạt f3 ≤ ε so với nghiệm MILP tương ứng.",
    "**Thời gian chạy** và **số lời giải không trội** của quần thể cuối.",
    "**Kiểm định.** Wilcoxon rank-sum hai phía trên HV giữa RP-MNSGA và từng thuật toán "
    "khác, hiệu chỉnh Holm trong mỗi instance, mức ý nghĩa 0,05; xếp hạng trung bình và "
    "kiểm định Friedman trên các instance.",
])
H2("5.4. Phân tích bổ sung")
bullets([
    "**Ablation:** lần lượt tắt từng thành phần trong ba thành phần cải tiến.",
    "**Độ nhạy** trên kroA100: mức ngân sách β ∈ {0,1; …; 0,6}, tầm bay R ∈ {8, 10, 12, "
    "16, 20} km, kích thước quần thể ∈ {50, 100, 200}; mỗi cấu hình 10 seed.",
    "**Khả năng mở rộng:** thời gian chạy và HV theo số điểm nhu cầu, tới 1.002 điểm.",
    "**Tái lập:** toàn bộ mã nguồn nằm trong uav_station_fleet.py; lệnh "
    "“python uav_station_fleet.py experiment” sinh lại mọi bảng và hình.",
])

# ============================================================================
# 6. Kết quả
# ============================================================================
H1("6. Kết quả")
G = S["greedy"]
imp = {i: (main[i]["RP-MNSGA"]["hv_mean"] / main[i]["NSGA-II"]["hv_mean"] - 1) * 100 for i in INSTS}
lo_i, hi_i = min(imp, key=imp.get), max(imp, key=imp.get)
wins = {a: [i for i in INSTS if main[i][a]["sign"] == "+"] for a in ALGOS if a != "RP-MNSGA"}

H2("6.1. So sánh tổng thể")


def cell(i, a, key):
    r = main[i][a]
    s = f"{vn(r[key + '_mean'])} ± {vn(r[key + '_std'])}"
    return s + (f" ({r['sign']})" if key == "hv" and r["sign"] else "")


table(f"Hypervolume (trung bình ± độ lệch chuẩn, {cfg['seeds']} seed; càng lớn càng tốt). "
      "Ký hiệu (+): RP-MNSGA tốt hơn có ý nghĩa thống kê; (=): không khác biệt; "
      "(−): RP-MNSGA kém hơn (Wilcoxon rank-sum, hiệu chỉnh Holm, α = 0,05).",
      ["Instance", "Greedy"] + ALGOS,
      [[i, vn(G[i]["hv"])] + [cell(i, a, "hv").replace("(-)", "(−)") for a in ALGOS] for i in INSTS],
      [1.7, 1.5, 2.6, 2.6, 2.6, 2.6, 2.4], size=8.5, bold_col=6)
para(f"Bảng 3 cho thấy RP-MNSGA đạt hypervolume trung bình cao hơn NSGA-II chuẩn trên cả "
     f"{len(INSTS)} instance, và khác biệt đều có ý nghĩa thống kê sau hiệu chỉnh Holm. "
     f"Mức cải thiện tương đối nhỏ nhất là {vn(imp[lo_i], 1)}% trên {lo_i} và lớn nhất là "
     f"{vn(imp[hi_i], 1)}% trên {hi_i}. Trên hai instance nhỏ nhất (eil51, berlin52), bài "
     f"toán đủ dễ để mọi biến thể tiến gần tới cùng một mặt Pareto nên chênh lệch dưới 1%; "
     f"từ 100 điểm nhu cầu trở lên, khoảng cách tăng lên 4–7%. Vì điểm tham chiếu là "
     f"(1,1; 1,1; 1,1), hypervolume tối đa về lý thuyết là 1,331 nên có giá trị lớn hơn 1.")
para("Greedy có hypervolume thấp hơn hẳn vì nó chỉ sinh các lời giải dùng bán kính phục "
     "vụ tối đa, tức chỉ đi dọc một đường theo hướng tăng độ phủ và không khai thác đánh "
     "đổi với thời gian phản ứng và năng lượng. Tuy vậy, xét riêng độ phủ thì greedy là "
     "một baseline mạnh: f3 nhỏ nhất của greedy trên pr299 là "
     f"{vn(G['pr299']['min_f3'] * 100, 1)}% so với {vn(main['pr299']['RP-MNSGA']['min_f3_mean'] * 100, 1)}% "
     "của RP-MNSGA, và tốt hơn NSGA-II chuẩn trên bốn instance lớn.")
table("IGD (trung bình ± độ lệch chuẩn; càng nhỏ càng tốt).",
      ["Instance", "Greedy"] + ALGOS,
      [[i, vn(G[i]["igd"])] + [cell(i, a, "igd") for a in ALGOS] for i in INSTS],
      [1.7, 1.5, 2.6, 2.6, 2.6, 2.6, 2.4], size=8.5, bold_col=6)
para("IGD cho cùng kết luận: RP-MNSGA có IGD trung bình thấp hơn NSGA-II trên mọi instance, "
     "với độ lệch chuẩn nhỏ hơn hoặc tương đương, tức kết quả ổn định hơn giữa các seed.")
table("Thứ hạng trung bình theo hypervolume trên 6 instance (1 là tốt nhất).",
      ["Thuật toán"] + ALGOS,
      [["Thứ hạng TB"] + [vn(S["friedman"]["avg_rank"][a], 2) for a in ALGOS]],
      [3.0, 2.6, 2.6, 2.6, 2.6, 2.6], size=10)
para(f"Kiểm định Friedman trên hypervolume trung bình của năm thuật toán tiến hóa cho "
     f"χ² = {vn(S['friedman']['stat'], 2)}, p = {vn(S['friedman']['p'], 4)}, tức có khác biệt "
     f"giữa các thuật toán ở mức 0,05. RP-MNSGA có thứ hạng trung bình tốt nhất, NSGA-II "
     f"chuẩn xếp cuối trên cả 6 instance. Do chỉ có 6 instance nên kiểm định hậu nghiệm "
     f"theo cặp trên thứ hạng không đủ lực; kết luận theo cặp dựa vào kiểm định Wilcoxon "
     f"trên 30 seed của từng instance ở Bảng 3.")

H2("6.2. Phân tích ablation")
para(f"Ba cột giữa của Bảng 3 cho biết đóng góp của từng thành phần. Bỏ **khởi tạo greedy** "
     f"làm hypervolume giảm có ý nghĩa trên {len(wins['w/o seeding'])}/6 instance "
     f"({', '.join(wins['w/o seeding'])}); đây là thành phần quan trọng nhất khi bài toán lớn. "
     f"Bỏ **repair** làm giảm có ý nghĩa trên {len(wins['w/o repair'])}/6 instance "
     f"({', '.join(wins['w/o repair'])}), nhưng trên pr299 và rat575 biến thể không repair "
     f"lại có hypervolume trung bình nhỉnh hơn một chút (không có ý nghĩa thống kê). Bỏ "
     f"**tìm kiếm cục bộ** chỉ làm giảm có ý nghĩa trên {len(wins['w/o LS'])}/6 instance "
     f"({', '.join(wins['w/o LS'])}).")
para("Như vậy câu trả lời cho RQ2 là có, nhưng không đồng đều: tổ hợp ba thành phần luôn "
     "thắng NSGA-II chuẩn, trong đó khởi tạo lai và repair đóng góp chính, còn tìm kiếm "
     "cục bộ đóng góp nhỏ. Trên instance lớn, mỗi lần repair tốn thêm một lần giải mã nên "
     "với cùng ngân sách đánh giá thuật toán chạy được ít thế hệ hơn, và lợi ích của repair "
     "bị triệt tiêu.")
figure("fig2_convergence.png",
       "Đường hội tụ hypervolume trung bình trên ba instance. Nét liền: NSGA-II và "
       "RP-MNSGA; nét đứt: các biến thể ablation.")
para("Hình 1 cho thấy lợi thế của RP-MNSGA xuất hiện từ rất sớm: trên kroA100 và rat575, "
     "sau khoảng 3.000–5.000 lần đánh giá thuật toán đã đạt mức hypervolume mà NSGA-II "
     "chuẩn cần toàn bộ 20.000 lần đánh giá mới tới. Biến thể không khởi tạo greedy xuất "
     "phát thấp và không đuổi kịp trong ngân sách đánh giá đã cho.")

H2("6.3. So sánh với nghiệm tối ưu MILP")
M = S["milp"]
rows = []
for i, m in M.items():
    for a in ("Greedy", "NSGA-II", "RP-MNSGA"):
        g = m["gaps"][a]
        r = [i if a == "Greedy" else "", vn(m["f3_star"] * 100, 1) + "%" if a == "Greedy" else "",
             a, vn(g["f3"] * 100, 2)]
        for pt in m["points"]:
            v = g[f"f2@{pt['eps']}"]
            full = 1 if a == "Greedy" else cfg["seeds"]
            if v["gap_pct"] is None:
                r.append("không đạt")
            else:
                r.append(vn(v["gap_pct"], 1) + "%" +
                         ("" if v["reached"] == full else f" ({v['reached']}/{full})"))
        rows.append(r)
table("Khoảng cách tới nghiệm MILP. Δf3: chênh lệch f3 nhỏ nhất so với f3* (điểm phần "
      "trăm). Ba cột cuối: chênh lệch tương đối của f2 nhỏ nhất trong các lời giải đạt "
      "f3 ≤ f3* + δ; (k/30) là số seed có lời giải đạt ngưỡng.",
      ["Instance", "f3* (MILP)", "Thuật toán", "Δf3", "δ = 0,05", "δ = 0,15", "δ = 0,30"],
      rows, [2.0, 2.0, 2.4, 1.6, 2.6, 2.6, 2.6], size=9.5, align_left=(0, 2))
para(f"HiGHS giải tối ưu cả ba instance (kroA100 có {M['kroA100']['vars']} biến nguyên, "
     f"mỗi bài toán con mất từ dưới 1 đến khoảng 15 giây). Về độ phủ, "
     f"RP-MNSGA cách nghiệm tối ưu f3* trung bình "
     f"{vn(M['eil51']['gaps']['RP-MNSGA']['f3'] * 100, 2)}; "
     f"{vn(M['berlin52']['gaps']['RP-MNSGA']['f3'] * 100, 2)} và "
     f"{vn(M['kroA100']['gaps']['RP-MNSGA']['f3'] * 100, 2)} điểm phần trăm trên ba instance, "
     f"trong khi NSGA-II chuẩn cách {vn(M['kroA100']['gaps']['NSGA-II']['f3'] * 100, 2)} "
     f"điểm phần trăm trên kroA100 và chỉ 4/30 seed tìm được lời giải trong ngưỡng δ = 0,05.")
para("Về năng lượng, khoảng cách của RP-MNSGA so với MILP dao động từ 0% đến khoảng 24% "
     "ở hầu hết các mức, nhưng lên tới 72,8% trên eil51 ở vùng độ phủ thấp (δ = 0,30). "
     "Đây là giới hạn của bộ giải mã chứ không phải của quá trình tìm kiếm: MILP được tự "
     "do chọn đúng những điểm gần trạm nhất để đạt ngưỡng phủ, còn bộ giải mã luôn ưu tiên "
     "điểm rủi ro cao và chỉ điều chỉnh vùng phục vụ qua bốn mức bán kính.")

H2("6.4. Mặt Pareto và cấu trúc lời giải")
figure("fig1_pareto.png",
       "Hai hình chiếu của mặt Pareto trên kroA100 (seed 0): độ phủ so với thời gian phản "
       "ứng (trái) và độ phủ so với năng lượng (phải). Điểm đen là nghiệm MILP.")
para("Hình 2 cho thấy rõ sự đánh đổi: giảm rủi ro không được phủ từ 60% xuống 20% làm thời "
     "gian phản ứng trung bình tăng từ khoảng 1,5 lên 3 phút và năng lượng tăng khoảng "
     "năm lần. Ở seed này hai mặt Pareto khá gần nhau; lời giải của RP-MNSGA nằm thấp hơn "
     "một chút ở vùng giữa và vươn tới độ phủ cao hơn (f3 khoảng 17% so với 20% của "
     "NSGA-II). Các điểm MILP nằm dưới cả hai, thể hiện khoảng cách năng lượng đã nêu ở "
     "Bảng 6. Các lời giải greedy nằm phía trên vì luôn dùng bán kính tối đa.")
figure("fig4_map.png",
       "Lời giải có độ phủ cao nhất của RP-MNSGA trên kroA100. Ô vuông là trạm sạc kèm số "
       "UAV; đoạn nối thể hiện phép gán; cỡ điểm tỉ lệ với trọng số rủi ro.")
para("Trong lời giải ở Hình 3, năm trạm với 19 UAV phủ khoảng 83% rủi ro. Số UAV phân bổ "
     "không đều (từ 2 đến 6 mỗi trạm) và tỉ lệ với khối lượng nhiệm vụ trong vùng phục vụ. "
     "Các điểm không được phủ gồm những điểm nằm ngoài tầm bay của mọi ứng viên và một cụm "
     "rủi ro cao ở góc dưới bên phải mà ngân sách không đủ để mở thêm trạm.")

H2("6.5. Phân tích độ nhạy")
sb, sr, sp = (S["sensitivity"][k] for k in ("sens_beta", "sens_range", "sens_pop"))
figure("fig3_sensitivity.png",
       "Rủi ro không được phủ nhỏ nhất mà RP-MNSGA đạt được trên kroA100 theo ngân sách "
       "(trái) và theo tầm bay (phải); trung bình 10 seed.")
table("Độ nhạy theo ngân sách trên kroA100 (lời giải có độ phủ cao nhất, trung bình 10 seed).",
      ["β", "Ngân sách B", "f3 nhỏ nhất", "f1 (phút)", "Số trạm", "Số UAV"],
      [[vn(d["beta"], 1), int(d["B"]), vn(d["min_f3"] * 100, 1) + "%", vn(d["f1_at_min_f3"], 2),
        vn(d["stations"], 1), vn(d["uavs"], 1)] for d in sb],
      [1.8, 2.8, 2.8, 2.6, 2.4, 2.4])
table("Độ nhạy theo tầm bay khứ hồi trên kroA100 (β = 0,3; trung bình 10 seed).",
      ["R (km)", "Phủ được tối đa", "f3 nhỏ nhất", "f1 (phút)", "Số trạm", "Số UAV"],
      [[int(d["range_km"]), vn(d["coverable"] * 100, 1) + "%", vn(d["min_f3"] * 100, 1) + "%",
        vn(d["f1_at_min_f3"], 2), vn(d["stations"], 1), vn(d["uavs"], 1)] for d in sr],
      [1.8, 3.2, 2.8, 2.6, 2.4, 2.4])
para(f"Theo ngân sách, rủi ro không được phủ giảm nhanh từ {vn(sb[0]['min_f3'] * 100, 1)}% "
     f"(β = 0,1) xuống {vn(sb[3]['min_f3'] * 100, 1)}% (β = 0,4), sau đó gần như đứng yên ở "
     f"mức {vn(sb[-1]['min_f3'] * 100, 1)}%, bằng đúng phần rủi ro nằm ngoài tầm bay của mọi "
     f"ứng viên. Điểm gãy nằm ở β = 0,4 (B = {int(sb[3]['B'])}, khoảng {vn(sb[3]['stations'], 0)} "
     f"trạm và {vn(sb[3]['uavs'], 0)} UAV). Vượt qua mức này, ngân sách tăng thêm chủ yếu được "
     f"dùng để mở thêm trạm, giúp giảm thời gian phản ứng từ {vn(sb[3]['f1_at_min_f3'], 2)} "
     f"xuống {vn(sb[-1]['f1_at_min_f3'], 2)} phút chứ không tăng độ phủ.")
para(f"Theo tầm bay, tăng R từ 8 lên 20 km giảm rủi ro không được phủ từ "
     f"{vn(sr[0]['min_f3'] * 100, 1)}% xuống {vn(sr[-1]['min_f3'] * 100, 1)}% với cùng mức ngân "
     f"sách, nhưng thời gian phản ứng trung bình tăng từ {vn(sr[0]['f1_at_min_f3'], 2)} lên "
     f"{vn(sr[-1]['f1_at_min_f3'], 2)} phút. Cấu trúc lời giải cũng đổi: số trạm giảm từ "
     f"{vn(sr[0]['stations'], 0)} xuống {vn(sr[-1]['stations'], 0)} trong khi số UAV tăng từ "
     f"{vn(sr[0]['uavs'], 0)} lên khoảng {vn(sr[-1]['uavs'], 0)}. Pin lớn hơn khiến phương án "
     f"ít trạm, mỗi trạm nhiều UAV trở nên có lợi.")
table("Độ nhạy theo kích thước quần thể trên kroA100.",
      ["Quần thể", "Số seed", "Hypervolume", "f3 nhỏ nhất"],
      [[d["pop"], d["runs"], f"{vn(d['hv'])} ± {vn(d['hv_std'])}", vn(d["min_f3"] * 100, 1) + "%"]
       for d in sp], [2.6, 2.4, 4.2, 3.2])
para("Kích thước quần thể 50 cho hypervolume thấp hơn rõ rệt vì mặt Pareto bị xấp xỉ bằng "
     "ít điểm hơn; tăng từ 100 lên 200 gần như không cải thiện thêm. Giá trị 100 dùng "
     "trong thực nghiệm chính là hợp lý với ngân sách 20.000 lần đánh giá.")

H2("6.6. Khả năng mở rộng")
sc = S["scalability"]
names = list(dict.fromkeys(s["instance"] for s in sc))
get = lambda n, a, k: next(s[k] for s in sc if s["instance"] == n and s["algo"] == a)
figure("fig5_scalability.png",
       "Thời gian chạy trung bình cho 20.000 lần đánh giá theo số điểm nhu cầu.", width_cm=10.5)
table("Thời gian chạy (giây) và hypervolume theo quy mô. pr1002 chạy 5 seed, các instance "
      "khác 30 seed.",
      ["Instance", "|I|", "|J|", "Thời gian NSGA-II", "Thời gian RP-MNSGA", "HV NSGA-II",
       "HV RP-MNSGA"],
      [[n, get(n, "NSGA-II", "I"), get(n, "NSGA-II", "J"), vn(get(n, "NSGA-II", "runtime"), 1),
        vn(get(n, "RP-MNSGA", "runtime"), 1), vn(get(n, "NSGA-II", "hv")),
        vn(get(n, "RP-MNSGA", "hv"))] for n in names],
      [2.0, 1.3, 1.3, 2.9, 3.1, 2.4, 2.6], size=10)
rt = lambda n: (get(n, "RP-MNSGA", "runtime") / get(n, "NSGA-II", "runtime") - 1) * 100
para(f"Thời gian chạy tăng gần tuyến tính theo số điểm nhu cầu, đúng với độ phức tạp "
     f"O(|I|·k) của bộ giải mã: từ khoảng 2 giây với 51 điểm lên "
     f"{vn(get('pr1002', 'RP-MNSGA', 'runtime'), 0)} giây với 1.002 điểm cho RP-MNSGA. Với "
     f"cùng số lần đánh giá, RP-MNSGA chậm hơn NSGA-II khoảng {vn(rt('rat575'), 0)}% trên "
     f"rat575 và {vn(rt('pr1002'), 0)}% trên pr1002, do phải tính lợi ích biên trong repair "
     f"và tìm kiếm cục bộ. Đổi lại, khoảng cách hypervolume không thu hẹp khi bài toán lớn "
     f"lên: trên pr1002 RP-MNSGA đạt {vn(get('pr1002', 'RP-MNSGA', 'hv'), 3)} so với "
     f"{vn(get('pr1002', 'NSGA-II', 'hv'), 3)} (5 seed, chưa kiểm định thống kê).")

# ============================================================================
# 7. Bình luận
# ============================================================================
H1("7. Bình luận")
H2("7.1. Trả lời các câu hỏi nghiên cứu")
bullets([
    "**RQ1.** Mặt Pareto cho thấy đánh đổi rõ giữa độ phủ với thời gian phản ứng và năng "
    "lượng. Với mức ngân sách β = 0,3, lời giải phủ nhiều nhất trên kroA100 dùng 5 trạm và "
    "19 UAV, phủ khoảng 83% rủi ro, cách nghiệm tối ưu MILP dưới 1 điểm phần trăm.",
    "**RQ2.** RP-MNSGA tốt hơn NSGA-II chuẩn có ý nghĩa thống kê trên cả 6 instance. Khởi "
    "tạo lai và repair là hai thành phần đóng góp chính; tìm kiếm cục bộ đóng góp nhỏ và "
    "chỉ có ý nghĩa trên một instance.",
    "**RQ3.** Lợi ích biên của ngân sách giảm nhanh và chạm trần ở mức phần rủi ro nằm "
    "trong tầm bay của các ứng viên. Tầm bay của pin ảnh hưởng cả đến độ phủ lẫn cấu trúc "
    "lời giải. Thời gian chạy tăng gần tuyến tính theo quy mô.",
])
H2("7.2. Ý nghĩa đối với người ra quyết định")
para("Điểm gãy trên đường ngân sách là thông tin hữu ích nhất: trên kroA100, tăng ngân sách "
     "quá mức β = 0,4 không mua thêm được độ phủ. Muốn phủ phần rủi ro còn lại thì phải bổ "
     "sung vị trí ứng viên hoặc dùng UAV có tầm bay lớn hơn, không phải mua thêm UAV. Kết "
     "quả theo tầm bay cũng cho thấy hai quyết định đặt trạm và xác định quy mô đội bay "
     "không tách rời được: khi pin lớn hơn, phương án tốt chuyển từ nhiều trạm nhỏ sang ít "
     "trạm lớn.")
H2("7.3. Vì sao các thành phần có hiệu quả")
para("Khởi tạo từ greedy đưa vào quần thể những cấu hình trạm đã phủ tốt các vùng rủi ro "
     "cao, là thứ mà khởi tạo ngẫu nhiên khó sinh ra khi số ứng viên lớn. Repair giữ lời "
     "giải khả thi mà không lãng phí ngân sách: bước loại UAV nhàn rỗi không làm đổi mục "
     "tiêu nhưng giải phóng chi phí, và bước cắt giảm ưu tiên giữ lại các trạm đang phủ "
     "nhiều rủi ro. Tìm kiếm cục bộ ít tác dụng hơn dự kiến; một cách giải thích là phần "
     "lớn các phép biến đổi của nó (thêm UAV theo lợi ích biên, đóng trạm yếu) trùng với "
     "những gì repair và khởi tạo greedy đã làm, nhưng giả thuyết này chưa được kiểm chứng "
     "riêng.")
H2("7.4. Hạn chế")
bullets([
    "Trọng số rủi ro và tần suất nhiệm vụ là dữ liệu tổng hợp. Dữ liệu OpenStreetMap và "
    "RescueNet/C2A nêu trong đề bài chưa được tích hợp, nên chưa có case study thực tế.",
    "Bộ giải mã ưu tiên rủi ro với bốn mức bán kính giới hạn không gian lời giải, thể hiện "
    "qua khoảng cách năng lượng so với MILP ở vùng độ phủ thấp.",
    "Chưa so sánh với MOEA/D hoặc NSGA-III; baseline tiến hóa duy nhất là NSGA-II.",
    "Khoảng cách là Euclid; chưa xét gió, địa hình, vùng cấm bay. Mỗi chuyến bay phục vụ "
    "một điểm, chưa có định tuyến qua nhiều điểm và chưa mô hình hàng đợi tại trạm sạc.",
    "Nhu cầu là tĩnh và tất định; chưa xét kịch bản bất định.",
])
H2("7.5. Các yếu tố ảnh hưởng tới độ tin cậy của kết luận")
para("Kết quả phụ thuộc vào cách sinh instance (vị trí ứng viên, điểm nóng rủi ro) với một "
     "seed duy nhất cho mỗi instance. Tham số của các thuật toán không được tinh chỉnh "
     "riêng; NSGA-II và RP-MNSGA dùng chung quần thể, xác suất lai và đột biến. Số lần đánh "
     "giá chỉ đếm các lần giải mã, không đếm phép tính lợi ích biên, nên báo cáo kèm cả thời "
     "gian chạy. Thí nghiệm trên pr1002 chỉ có 5 seed và kiểm định Friedman chỉ dựa trên 6 "
     "instance.")

# ============================================================================
# 8. Kết luận
# ============================================================================
H1("8. Kết luận và hướng phát triển")
para(f"Báo cáo mô hình hóa bài toán đặt trạm sạc và xác định quy mô đội UAV dưới dạng tối ưu "
     f"ba mục tiêu và đề xuất RP-MNSGA, một NSGA-II lai có repair ưu tiên rủi ro. Trên 6 "
     f"instance TSPLIB với 30 seed, RP-MNSGA cải thiện hypervolume so với NSGA-II chuẩn từ "
     f"{vn(imp[lo_i], 1)}% đến {vn(imp[hi_i], 1)}%, có ý nghĩa thống kê trên mọi instance, và "
     f"đạt độ phủ cách nghiệm tối ưu MILP không quá "
     f"{vn(max(M[i]['gaps']['RP-MNSGA']['f3'] for i in M) * 100, 1)} điểm phần trăm trên các "
     f"instance nhỏ.")
para("Hướng phát triển gồm: (1) tích hợp dữ liệu thực từ OpenStreetMap và RescueNet/C2A; "
     "(2) thay bộ giải mã bằng một bước gán tối ưu hơn để thu hẹp khoảng cách năng lượng so "
     "với MILP; (3) mở rộng sang nhu cầu bất định theo kịch bản và tối ưu robust; (4) so "
     "sánh với MOEA/D và NSGA-III; (5) kết hợp định tuyến nhiều điểm và trạm sạc di động "
     "trên xe mặt đất theo hướng của Wang và cộng sự [9].")

# ============================================================================
# Tài liệu tham khảo
# ============================================================================
H1("Tài liệu tham khảo")
REFS = [
    "S. L. Hakimi, “Optimum locations of switching centers and the absolute centers and medians of a graph,” Operations Research, 12(3), 450–459, 1964.",
    "C. Toregas, R. Swain, C. ReVelle, L. Bergman, “The location of emergency service facilities,” Operations Research, 19(6), 1363–1373, 1971.",
    "R. Church, C. ReVelle, “The maximal covering location problem,” Papers of the Regional Science Association, 32, 101–118, 1974.",
    "M. S. Daskin, “A maximum expected covering location model: formulation, properties and heuristic solution,” Transportation Science, 17(1), 48–70, 1983.",
    "I. Hong, M. Kuby, A. T. Murray, “A range-restricted recharging station coverage model for drone delivery service planning,” Transportation Research Part C, 90, 198–212, 2018.",
    "D. Chauhan, A. Unnikrishnan, M. Figliozzi, “Maximum coverage capacitated facility location problem with range constrained drones,” Transportation Research Part C, 99, 1–18, 2019.",
    "J. J. Boutilier và cộng sự, “Optimizing a drone network to deliver automated external defibrillators,” Circulation, 135(25), 2454–2465, 2017.",
    "Z. Ghelichi, M. Gentili, P. B. Mirchandani, “Logistics for a fleet of drones for medical item delivery: A case study for Louisville, KY,” Computers & Operations Research, 135, 105443, 2021.",
    "Wang và cộng sự, “UAV–Ground Vehicle Collaborative Delivery in Emergency …,” 2025. [Bổ sung tên đầy đủ và nơi công bố theo tài liệu của học phần]",
    "K. Deb, A. Pratap, S. Agarwal, T. Meyarivan, “A fast and elitist multiobjective genetic algorithm: NSGA-II,” IEEE Transactions on Evolutionary Computation, 6(2), 182–197, 2002.",
    "Q. Zhang, H. Li, “MOEA/D: A multiobjective evolutionary algorithm based on decomposition,” IEEE Transactions on Evolutionary Computation, 11(6), 712–731, 2007.",
    "K. Deb, H. Jain, “An evolutionary many-objective optimization algorithm using reference-point-based nondominated sorting approach, Part I,” IEEE Transactions on Evolutionary Computation, 18(4), 577–601, 2014.",
    "M. B. Teitz, P. Bart, “Heuristic methods for estimating the generalized vertex median of a weighted graph,” Operations Research, 16(5), 955–961, 1968.",
    "G. L. Nemhauser, L. A. Wolsey, M. L. Fisher, “An analysis of approximations for maximizing submodular set functions—I,” Mathematical Programming, 14, 265–294, 1978.",
    "G. Reinelt, “TSPLIB—A traveling salesman problem library,” ORSA Journal on Computing, 3(4), 376–384, 1991.",
    "E. Zitzler, L. Thiele, “Multiobjective evolutionary algorithms: a comparative case study and the strength Pareto approach,” IEEE Transactions on Evolutionary Computation, 3(4), 257–271, 1999.",
]
for k, r in enumerate(REFS, 1):
    p = para(f"[{k}] {r}", size=12, indent=False, after=3)
    p.paragraph_format.left_indent = Cm(0.9)
    p.paragraph_format.first_line_indent = Cm(-0.9)

# ---- Tóm tắt (điền vào vị trí đã giữ chỗ) ----
ABSTRACT = (
    f"Vị trí trạm sạc và quy mô đội bay quyết định khả năng phản ứng của UAV trong ứng phó "
    f"thiên tai. Báo cáo mô hình hóa bài toán chọn trạm sạc, số UAV mỗi trạm và vùng phục vụ "
    f"dưới dạng tối ưu ba mục tiêu (thời gian phản ứng có trọng số rủi ro, năng lượng, rủi "
    f"ro không được phủ) với ràng buộc pin, năng lực đội bay và ngân sách. Thuật toán đề "
    f"xuất RP-MNSGA là một NSGA-II lai gồm mã hóa rút gọn, bộ giải mã ưu tiên rủi ro, cơ chế "
    f"repair, tìm kiếm cục bộ và khởi tạo từ greedy. Trên 6 instance TSPLIB (51–575 điểm, "
    f"30 seed, 20.000 lần đánh giá), RP-MNSGA có hypervolume cao hơn NSGA-II chuẩn từ "
    f"{vn(imp[lo_i], 1)}% đến {vn(imp[hi_i], 1)}%, có ý nghĩa thống kê trên mọi instance "
    f"(Wilcoxon, hiệu chỉnh Holm), và đạt độ phủ cách nghiệm tối ưu MILP không quá "
    f"{vn(max(M[i]['gaps']['RP-MNSGA']['f3'] for i in M) * 100, 1)} điểm phần trăm trên ba "
    f"instance nhỏ. Phân tích ablation cho thấy khởi tạo lai và repair là hai thành phần đóng "
    f"góp chính. Phân tích độ nhạy chỉ ra điểm gãy của ngân sách, sau đó độ phủ không tăng "
    f"thêm. Hạn chế chính: trọng số rủi ro là dữ liệu tổng hợp và bộ giải mã còn cách MILP "
    f"về năng lượng ở vùng độ phủ thấp.")
ABSTRACT_ANCHOR.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
ABSTRACT_ANCHOR.add_run(ABSTRACT).italic = True
kw = doc.add_paragraph()
ABSTRACT_ANCHOR._p.addnext(kw._p)
kw.add_run("Từ khóa: ").bold = True
kw.add_run("UAV, trạm sạc, facility location, fleet sizing, tối ưu đa mục tiêu, NSGA-II, "
           "thuật toán memetic, constraint repair.")

out = os.path.join(ROOT, "BaoCao_Nhom8_UAV.docx")
doc.save(out)
print("Đã ghi", out)
