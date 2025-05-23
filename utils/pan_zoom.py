from PIL import ImageTk

def pan_and_zoom(canvas, image, screen_width, screen_height):
    # Zoom à 1.2x
    zoom_factor = 1.2
    img_width, img_height = image.size
    zoomed_width = int(img_width * zoom_factor)
    zoomed_height = int(img_height * zoom_factor)

    image_zoomed = image.resize((zoomed_width, zoomed_height), Image.LANCZOS)

    dx = (zoomed_width - screen_width) // 20
    dy = (zoomed_height - screen_height) // 20

    frames = []

    for step in range(20):
        left = dx * step
        top = dy * step
        box = (left, top, left + screen_width, top + screen_height)
        cropped = image_zoomed.crop(box)
        tk_img = ImageTk.PhotoImage(cropped)
        frames.append(tk_img)

    def animate(frame_idx=0):
        if frame_idx < len(frames):
            canvas.delete("all")
            canvas.create_image(0, 0, image=frames[frame_idx], anchor="nw")
            canvas.image = frames[frame_idx]
            canvas.after(50, animate, frame_idx + 1)

    animate()

def display_static_image(canvas, image, screen_width, screen_height):
    img_width, img_height = image.size
    x = (screen_width - img_width) // 2
    y = (screen_height - img_height) // 2
    tk_img = ImageTk.PhotoImage(image)
    canvas.delete("all")
    canvas.create_image(x, y, image=tk_img, anchor="nw")
    canvas.image = tk_img
