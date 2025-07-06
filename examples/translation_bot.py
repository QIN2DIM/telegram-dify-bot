# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/7 05:03
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :

**一种快速实现的多语种多路翻译器**

Roadmap
-------
1. 支持文本模态的多语种翻译
    - 默认提供 any_language to type(language_code) 的翻译
2. 加入图文混合模态的多语种翻译（原石内容提取 + 可选的语种输出翻译）
3. 有效处理表格型图片输入

Advanced
--------
1. 交互优化：有效处理即时通信场景中的碎片消息翻译问题，代入充足的上下文信息以复原完整的深层意图
2. 意图分类器：在 Chatflow 中添加 Node + Telegram Bot Command 的功能和模式分流
3. 用户偏好、会话管理与长期记忆：
    - 如何感知、记忆和回调用户偏好？
    - 当前场景更适合 Chatflow 还是 Workflow？如何应对用户对翻译结果的编辑要求？

IF Workflow
-----------
YES:
- 极简设计，无需管理复杂的 OAI 多轮对话对象，所有 **文本模态** 历史操作记忆都可通过 Telegram API 获取并作为 user_prompt 的一部分单次请求

BUT:
- 机器人需要知道一定记忆窗口内的历史翻译记录（IN&OUT），否则无法应对碎片消息和二次编辑需求。如果不是 ALL 那必然设置一个窗口，如何设计这个窗口？

IF Chatflow
-----------
YES:

BUT:
1. 需要足够好的策略切分 Conversation/GroupChat/Users 的多对多映射关系。

Optimization:
1. 提高响应速度
2. 触发渠道优化
3. 权限控制
4. 适当的审查和拒绝响应
5. Ratelimit Queue
"""
