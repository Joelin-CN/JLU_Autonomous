name: 刷课需求
description: 提交一个需要管理者处理的网课自动化需求
title: "[需求] <课程名> - <平台>"
labels: ["brush-request", "status/pending"]
body:
  - type: markdown
    attributes:
      value: |
        > ⚠️ **隐私警告（公开仓库，全网可见）**
        > **禁止**在本 Issue 及其评论中填写：手机号、密码、验证码、真实姓名、学号、API Key。
        > 账号凭据请线下交给接单管理者；这里只登记课程与进度。

  - type: dropdown
    id: platform
    attributes:
      label: 平台
      options:
        - 超星学习通
        - 智慧树（暂未支持，仅登记）
    validations:
      required: true

  - type: input
    id: course
    attributes:
      label: 课程名称
      description: 需要处理的课程，多门课程用顿号分隔
      placeholder: 例如：概率论与数理统计
    validations:
      required: true

  - type: textarea
    id: scope
    attributes:
      label: 处理范围
      description: 希望完成的内容
      placeholder: 例如：全部视频章节 + 章节测验（测验目标分数 100）
    validations:
      required: true

  - type: input
    id: deadline
    attributes:
      label: 期望完成时间
      placeholder: 例如：2026-09-15 前
    validations:
      required: false

  - type: textarea
    id: notes
    attributes:
      label: 补充说明
      description: 特殊要求（仅刷某几章 / 跳过某类题型等）。凭据交接情况也在这里备注（如「账号线下已交」）
    validations:
      required: false

  - type: markdown
    attributes:
      value: |
        **管理者专用（提交者勿填）**：接手时把自己设为 assignee 并把标签改为 `status/in-progress`；完成后改为 `status/done` 并评论结果。流程见 [CONTRIBUTING.md §4](https://github.com/Joelin-CN/JLU_Autonomous/blob/main/CONTRIBUTING.md)。
