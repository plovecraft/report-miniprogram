from docx import Document

from backend.app.services.report_inspector import update_report_header_fields


def test_updates_project_name_by_label_without_touching_instructor() -> None:
    doc = Document()
    table = doc.add_table(rows=4, cols=4)
    table.rows[2].cells[0].text = "实验项目名称"
    table.rows[2].cells[1].text = "旧项目"
    table.rows[2].cells[2].text = "指导老师"
    table.rows[2].cells[3].text = "李老师"

    update_report_header_fields(doc, {"experimentName": "实验三  天塔之光模拟控制"})

    assert table.rows[2].cells[0].text == "实验项目名称"
    assert table.rows[2].cells[1].text == "实验三  天塔之光模拟控制"
    assert table.rows[2].cells[2].text == "指导老师"
    assert table.rows[2].cells[3].text == "李老师"


def test_updates_known_student_fields_and_skips_missing_values() -> None:
    doc = Document()
    table = doc.add_table(rows=4, cols=6)
    table.rows[0].cells[0].text = "班级"
    table.rows[0].cells[1].text = ""
    table.rows[0].cells[2].text = "姓名"
    table.rows[0].cells[3].text = ""
    table.rows[0].cells[4].text = "学号"
    table.rows[0].cells[5].text = ""
    table.rows[2].cells[0].text = "指导老师"
    table.rows[2].cells[1].text = "王老师"

    update_report_header_fields(
        doc,
        {
            "className": "机器234",
            "studentName": "吴梓添",
            "studentId": "32307700156",
        },
    )

    assert table.rows[0].cells[1].text == "机器234"
    assert table.rows[0].cells[3].text == "吴梓添"
    assert table.rows[0].cells[5].text == "32307700156"
    assert table.rows[2].cells[1].text == "王老师"


def test_updates_course_teacher_colleges_lab_and_date_by_labels() -> None:
    doc = Document()
    table = doc.add_table(rows=3, cols=8)
    table.rows[0].cells[0].text = "用户学院"
    table.rows[0].cells[1].text = "原用户学院"
    table.rows[0].cells[2].text = "班级"
    table.rows[0].cells[3].text = "原班级"
    table.rows[1].cells[0].text = "课程名称"
    table.rows[1].cells[1].text = "原课程"
    table.rows[1].cells[2].text = "开课学院及实验室"
    table.rows[1].cells[3].text = "原实验室"
    table.rows[1].cells[4].text = "日期"
    table.rows[1].cells[5].text = "旧日期"
    table.rows[2].cells[0].text = "指导老师"
    table.rows[2].cells[1].text = "原老师"

    update_report_header_fields(
        doc,
        {
            "studentCollege": "机械与电气工程学院",
            "className": "机器234",
            "courseName": "可编程控制器",
            "offeringCollegeLab": "自动化学院 PLC 实验室",
            "teacherName": "李老师",
            "date": "2026年05月07日",
        },
    )

    assert table.rows[0].cells[1].text == "机械与电气工程学院"
    assert table.rows[0].cells[3].text == "机器234"
    assert table.rows[1].cells[1].text == "可编程控制器"
    assert table.rows[1].cells[3].text == "自动化学院 PLC 实验室"
    assert table.rows[1].cells[5].text == "2026年05月07日"
    assert table.rows[2].cells[1].text == "李老师"


def test_updates_standalone_date_paragraph() -> None:
    doc = Document()
    doc.add_paragraph("广州大学学生实验报告")
    doc.add_paragraph("2025年03月01日")
    doc.add_table(rows=1, cols=1)

    update_report_header_fields(doc, {"date": "2026年05月07日"})

    assert doc.paragraphs[1].text == "2026年05月07日"


def test_updates_real_template_outside_header_and_table_labels() -> None:
    doc = Document()
    doc.add_paragraph("开课学院及实验室：  机械与电气工程学院                         2025 年 10 月 15 日")
    table = doc.add_table(rows=3, cols=8)
    table.rows[0].cells[0].text = "学院"
    table.rows[0].cells[1].text = "机械与电"
    table.rows[0].cells[2].text = "年级、专\n业、班"
    table.rows[0].cells[3].text = "机器 221"
    table.rows[0].cells[4].text = "姓名"
    table.rows[0].cells[5].text = "旧姓名"
    table.rows[0].cells[6].text = "学号"
    table.rows[0].cells[7].text = "旧学号"
    table.rows[1].cells[0].text = "实验课程名称"
    table.rows[1].cells[1].text = "单片机微机实验"
    table.rows[2].cells[0].text = "实验项目名称"
    table.rows[2].cells[1].text = "旧项目"
    table.rows[2].cells[6].text = "指导\n老师"
    table.rows[2].cells[7].text = "旧老师"

    update_report_header_fields(
        doc,
        {
            "studentCollege": "机械与电气工程学院",
            "className": "机器234",
            "studentName": "吴梓添",
            "studentId": "32307700156",
            "courseName": "可编程控制器实验",
            "experimentName": "实验三  天塔之光模拟控制",
            "teacherName": "李老师",
            "offeringCollegeLab": "自动化学院 PLC 实验室",
            "date": "2026 年 05 月 07 日",
        },
    )

    assert "开课学院及实验室：  自动化学院 PLC 实验室" in doc.paragraphs[0].text
    assert "2026 年 05 月 07 日" in doc.paragraphs[0].text
    assert table.rows[0].cells[1].text == "机械与电气工程学院"
    assert table.rows[0].cells[3].text == "机器234"
    assert table.rows[0].cells[5].text == "吴梓添"
    assert table.rows[0].cells[7].text == "32307700156"
    assert table.rows[1].cells[1].text == "可编程控制器实验"
    assert table.rows[2].cells[1].text == "实验三  天塔之光模拟控制"
    assert table.rows[2].cells[7].text == "李老师"


def test_updates_placeholder_date_in_real_template_header_line() -> None:
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("开课学院及实验室：")
    paragraph.add_run("机械与电气工程学院")
    paragraph.add_run("  ")
    paragraph.add_run("\t")
    paragraph.add_run("\t")
    paragraph.add_run("\t")
    paragraph.add_run("\t")
    paragraph.add_run("          ")
    paragraph.add_run("年")
    paragraph.add_run(" ")
    paragraph.add_run("月")
    paragraph.add_run(" ")
    paragraph.add_run("日")
    doc.add_table(rows=1, cols=1)

    update_report_header_fields(doc, {"date": "2026 年 05 月 08 日"})

    assert "机械与电气工程学院" in doc.paragraphs[0].text
    assert "2026 年 05 月 08 日" in doc.paragraphs[0].text
    assert "年 月 日" not in doc.paragraphs[0].text
