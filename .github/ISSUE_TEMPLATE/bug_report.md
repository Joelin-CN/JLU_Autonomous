name: 问题反馈
description: 报告一个缺陷或异常行为
title: "[bug] <一句话描述>"
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: |
        > ⚠️ 公开仓库：日志 / 截图中的手机号、姓名、课程 ID 请先打码（格式参考 `132****3918`）。禁止粘贴任何凭据。
  - type: textarea
    id: what-happened
    attributes:
      label: 问题描述
      description: 发生了什么、期望是什么
    validations:
      required: true
  - type: dropdown
    id: area
    attributes:
      label: 影响区域
      options:
        - 前端（Electron / Vue）
        - 后端（Python / 浏览器自动化）
        - AI 答题
        - 打包 / 安装
        - 其他
    validations:
      required: true
  - type: textarea
    id: repro
    attributes:
      label: 复现步骤
      placeholder: |
        1. 进入 ……
        2. 点击 ……
        3. 出现 ……
    validations:
      required: true
  - type: textarea
    id: logs
    attributes:
      label: 相关日志 / 截图
      description: 已脱敏的日志片段或截图
    validations:
      required: false
  - type: input
    id: version
    attributes:
      label: 版本 / 环境
      placeholder: 例如：main@<commit>，Windows 11，Python 3.13
    validations:
      required: false
