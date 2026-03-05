import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(__file__))

from ui.app import MainApp


def main():
    app = MainApp()
    app.mainloop()


if __name__ == "__main__":
    main()
