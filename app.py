import sys


def worker_streams():
    """File channels avoid unavailable stdio in windowed frozen executables."""
    if "--job-file" in sys.argv and "--events-file" in sys.argv:
        import os
        job = sys.argv[sys.argv.index("--job-file") + 1]
        events = sys.argv[sys.argv.index("--events-file") + 1]
        sys.stdin = open(job, "r", encoding="utf-8")
        sys.stdout = open(events, "w", encoding="utf-8", buffering=1)
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


if __name__ == "__main__":
    if "--worker" in sys.argv:
        worker_streams()
        from wsi_app.worker import main
    else:
        from wsi_app.gui import main
    raise SystemExit(main())
