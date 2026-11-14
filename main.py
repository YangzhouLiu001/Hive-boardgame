# -*- coding: utf-8 -*-
"""虫虫蜂房 · Hive —— 本地版入口。

双击运行，或 python main.py
"""

import faulthandler
import os
import sys
import threading
import time
import traceback


def _bootstrap():
    # 打包成 exe 时用的是内置模块，不要把源码目录塞进 sys.path，
    # 否则会盖掉打包进去的 hive 包。
    if getattr(sys, "frozen", False):
        return
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)


_CRASH = None


def _open_crash_log():
    """所有异常/硬崩溃都往这个文件里写，打包后没有控制台也能查。"""
    global _CRASH
    try:
        from hive import store
        p = os.path.join(store.app_dir(), "crash.log")
        _CRASH = open(p, "a", buffering=1, encoding="utf-8")
        _CRASH.write("\n=== 启动 %s ===\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        faulthandler.enable(file=_CRASH)
    except Exception:
        _CRASH = None


def _hook():
    def excepthook(tp, val, tb):
        try:
            if _CRASH:
                _CRASH.write("[主线程异常]\n")
                traceback.print_exception(tp, val, tb, file=_CRASH)
        except Exception:
            pass
        sys.__excepthook__(tp, val, tb)

    def threadhook(args):
        try:
            if _CRASH:
                _CRASH.write("[线程异常] %s\n" % (args.thread.name,))
                traceback.print_exception(args.exc_type, args.exc_value,
                                          args.exc_traceback, file=_CRASH)
        except Exception:
            pass

    sys.excepthook = excepthook
    threading.excepthook = threadhook

    # Tk 回调里的异常默认只往 stderr 打，打包后等于消失，这里截下来
    try:
        import tkinter
        orig = tkinter.Tk.report_callback_exception

        def report(self, exc, val, tb):
            try:
                if _CRASH:
                    _CRASH.write("[Tk 回调异常]\n")
                    traceback.print_exception(exc, val, tb, file=_CRASH)
            except Exception:
                pass
            orig(self, exc, val, tb)

        tkinter.Tk.report_callback_exception = report
    except Exception:
        pass


def main():
    _bootstrap()
    _open_crash_log()
    _hook()
    try:
        from hive.ui import main as run
        run()
    except Exception:
        import traceback as tb
        from hive import store
        p = os.path.join(store.app_dir(), "error.log")
        with open(p, "w", encoding="utf-8") as f:
            f.write(tb.format_exc())
        try:
            import tkinter.messagebox as mb
            mb.showerror("虫虫蜂房 出错了", "程序遇到问题：\n\n%s\n\n详情见：%s"
                         % (sys.exc_info()[1], p))
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
