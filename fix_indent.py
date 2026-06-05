#!/usr/bin/env python3
# 修复 ws_server.py 缩进问题

with open('ws_server.py', 'r') as f:
    lines = f.readlines()

# 修复第627-633行 (0-indexed: 626-632)
# 这些行应该在 text 处理块内，但缩进错了
for i in range(626, 633):  # 627-633行
    if i < len(lines):
        content = lines[i].rstrip()
        if content:
            # 去掉前导空格，重新加12空格
            stripped = content.lstrip()
            if stripped:  # 非空行
                lines[i] = '            ' + stripped + '\n'

# 写入
with open('ws_server.py', 'w') as f:
    f.writelines(lines)

print("修复完成: 第627-633行缩进已调整为12空格")
