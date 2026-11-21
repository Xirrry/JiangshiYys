# 神秘商店读取组件

`shop_read.py` 仅获取当前游戏进程已加载的商店缓存和客户端展示 getter，不执行购买、刷新、分享请求。

修改脚本后运行 `python build_agent.py` 再运行 `build-shop.cmd`。宿主通过 bounty_transport 校验目标 PID 与创建时间，调用本组件并接收 JSON。

启动器页面位于侧栏「神秘商店」，存档在 data/mystery-shop.sqlite3。源码工作区首次进入时导入 experiments/mystery-shop/shop-cache.json，原文件保留。

商品羁绊字段 intimat：0 不限，1 友谊的见证，2 温暖的陪伴，3 永远的羁绊。太鼓名称按游戏配置保留星级。数字标识不在界面显示。

验证：release_tools/test_mystery_shop.py、release_tools/test_shop_launcher_ui.cjs。前端测试使用本机 5194 端口的 Vite 服务。
