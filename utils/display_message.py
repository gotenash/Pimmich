import pygame
import sys
import os

def draw_text(surface, text, font, color, center_pos):
    """Dessine du texte centré sur une position donnée."""
    text_surface = font.render(text, True, color)
    text_rect = text_surface.get_rect(center=center_pos)
    surface.blit(text_surface, text_rect)

def main():
    """Affiche un message centré sur l'écran pendant un court instant."""
    if len(sys.argv) < 2:
        print("Usage: python display_message.py \"Votre message\"")
        return

    message = sys.argv[1]

    # Assurer que l'environnement d'affichage est correctement configuré
    if "SWAYSOCK" not in os.environ:
        # Logique de fallback si la variable n'est pas définie
        # (peut être nécessaire si appelé depuis un contexte inattendu)
        user_id = os.getuid()
        sock_path_pattern = f"/run/user/{user_id}/sway-ipc.*"
        import glob
        socks = glob.glob(sock_path_pattern)
        if socks:
            os.environ["SWAYSOCK"] = socks[0]

    pygame.init()

    info = pygame.display.Info()
    screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
    screen.fill((0, 0, 0)) # Fond noir

    font = pygame.font.Font(None, 60) # Police par défaut, taille 60
    draw_text(screen, message, font, (255, 255, 255), screen.get_rect().center)
    pygame.display.flip()

if __name__ == "__main__":
    main()