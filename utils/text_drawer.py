import pygame

def draw_text_with_outline(screen, text, font, text_color, outline_color, pos, anchor="center"):
    """
    Dessine du texte sur une surface Pygame avec un contour pour une meilleure lisibilité.

    Args:
        screen (pygame.Surface): La surface sur laquelle dessiner.
        text (str): Le texte à afficher.
        font (pygame.font.Font): La police à utiliser.
        text_color (tuple): La couleur du texte (R, G, B).
        outline_color (tuple): La couleur du contour (R, G, B).
        pos (tuple): La position (x, y) du texte.
        anchor (str): Le point d'ancrage pour la position ('center', 'topleft', etc.).
    """
    # Rendu des surfaces une seule fois
    text_surface = font.render(text, True, text_color)
    outline_surface = font.render(text, True, outline_color)

    # Obtenir le rectangle pour le positionnement
    text_rect = text_surface.get_rect(**{anchor: pos})
    
    # Dessiner le contour en décalant la surface
    offsets = [(-2, -2), (-2, 2), (2, -2), (2, 2)]
    for ox, oy in offsets:
        screen.blit(outline_surface, text_rect.move(ox, oy))
    
    # Dessiner le texte principal
    screen.blit(text_surface, text_rect)