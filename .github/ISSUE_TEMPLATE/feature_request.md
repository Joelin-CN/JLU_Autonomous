name: 功能建议
description: 提出新功能或改进建议
title: "[feature] <一句话描述>"
labels: ["enhancement"]
body:
  - type: textarea
    id: problem
    attributes:
      label: 想解决的问题
      description: 这个功能解决什么痛点（先说问题，再说方案）
    validations:
      required: true
  - type: textarea
    id: solution
    attributes:
      label: 期望的方案
      description: 你希望它怎么工作
    validations:
      required: true
  - type: dropdown
    id: platform
    attributes:
      label: 相关平台
      options:
        - 通用（跨平台）
        - 超星学习通
        - 智慧树
        - 前端 / 桌面端
    validations:
      required: true
  - type: textarea
    id: alternatives
    attributes:
      label: 备选方案 / 参考
      description: 你考虑过的其他做法、参考项目链接
    validations:
      required: false
