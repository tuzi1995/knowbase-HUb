import os
import argparse
from datetime import datetime

from openpyxl import Workbook


FALLBACK_ENCODINGS = ["utf-8", "gbk", "gb2312"]


def read_file_with_encodings(path):
    last_error = None
    for enc in FALLBACK_ENCODINGS:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc
        except UnicodeDecodeError as e:
            last_error = e
            continue
    if last_error is not None:
        raise last_error
    raise UnicodeDecodeError("unknown", b"", 0, 1, "unable to decode file")


def process_folder(folder, output_name="markdown汇总.xlsx", log_name="error_log.txt"):
    folder = os.path.abspath(folder)

    all_entries = os.listdir(folder)
    md_files = []
    for name in all_entries:
        if name.startswith("."):
            continue
        full_path = os.path.join(folder, name)
        if not os.path.isfile(full_path):
            continue
        if not name.lower().endswith(".md"):
            continue
        md_files.append(name)

    md_files.sort()

    total = len(md_files)
    success = 0
    failed = 0

    log_path = os.path.join(folder, log_name)
    if os.path.exists(log_path):
        os.remove(log_path)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "markdown"
    worksheet.append(["文件名", "内容"])

    with open(log_path, "a", encoding="utf-8") as log:
        log.write("开始时间: " + datetime.now().isoformat() + "\n")
        log.write("目标文件夹: " + folder + "\n")
        log.write("发现 markdown 文件数量: " + str(total) + "\n\n")

        for index, filename in enumerate(md_files, start=1):
            print("正在处理第{}个文件：{}".format(index, filename))
            file_path = os.path.join(folder, filename)
            try:
                content, used_encoding = read_file_with_encodings(file_path)
                worksheet.append([filename, content])
                success += 1
            except Exception as exc:
                failed += 1
                log.write("[失败] 文件: {} 错误: {}\n".format(filename, repr(exc)))

        log.write("\n成功: " + str(success) + ", 失败: " + str(failed) + "\n")
        log.write("结束时间: " + datetime.now().isoformat() + "\n")

    output_path = os.path.join(folder, output_name)
    workbook.save(output_path)

    print("处理完成，总计 {} 个文件，成功 {} 个，失败 {} 个".format(total, success, failed))
    print("Excel 已生成：{}".format(output_path))
    print("错误日志：{}".format(log_path))


def main():
    parser = argparse.ArgumentParser(
        description="批量读取markdown文件并汇总到Excel"
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=r"D:\AI处理\accessory_markdown",
        help="包含markdown文件的目标文件夹，默认为 D:\\AI处理\\accessory_markdown",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="markdown汇总.xlsx",
        help="输出的Excel文件名，默认为 markdown汇总.xlsx",
    )
    parser.add_argument(
        "--log",
        "-l",
        default="error_log.txt",
        help="错误日志文件名，默认为 error_log.txt",
    )

    args = parser.parse_args()
    process_folder(args.folder, args.output, args.log)


if __name__ == "__main__":
    main()

