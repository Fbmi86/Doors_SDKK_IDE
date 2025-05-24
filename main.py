import tkinter as tk
from sdkk_builder_gui import SDKKBuilderGUI

def main():
    """
    Main entry point for the Doors SDKK Builder application.
    Initializes the Tkinter root window and the GUI application.
    """
    root = tk.Tk()
    app = SDKKBuilderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
