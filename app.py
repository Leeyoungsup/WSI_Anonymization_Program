import sys

if __name__ == "__main__":
    if "--worker" in sys.argv:
        from wsi_app.worker import main
    else:
        from wsi_app.gui import main
    raise SystemExit(main())
