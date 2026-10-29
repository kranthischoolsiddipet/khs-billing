import os
import sys
from PIL import Image

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(base_dir, "khs_logo.png")
    ico_path = os.path.join(base_dir, "khs_logo.ico")
    
    if os.path.exists(png_path) and not os.path.exists(ico_path):
        img = Image.open(png_path)
        img.save(ico_path, format='ICO', sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
        print("Generated khs_logo.ico")

if __name__ == "__main__":
    main()
