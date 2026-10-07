from rembg import remove, new_session
from PIL import Image

def remove_background(model, dest):
    session = new_session(model)
    input = Image.open(dest)
    output = remove(input, session=session, bgcolor=(255,255,255,255))
    print(f"salvando em: {dest}")
    output.save(dest)