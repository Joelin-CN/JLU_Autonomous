# data/

项目运行时数据目录（**git 忽略，不入库**）。本文件仅作索引说明。

| 子目录 | 用途 |
| --- | --- |
| passwords/ | 凭证文件：`chaoxing.txt`（超星账号）、`doubao.txt`（豆包密钥）、`volc_billing.txt`（火山 AK/SK） |
| chrome-profiles/ | 浏览器持久化档案（登录态，敏感） |
| screenshots/ | 手动 / 调试截图 |
| output/ | 进度状态、课程发现快照、答题统计 |
| temp/ | 临时 JS 脚本、题目 / 验证码截图 |
| logs/ | 按日滚动的运行日志与异常日志 |
| documents/ | 个人参考文档（PDF 等） |

> 打包安装后，这些目录落在 `%APPDATA%/超星助手/data/`；开发模式下即仓库根 `data/`。
