"""Mi juego AURA: flechas/WASD para mover; espacio cambia color; Escape sale."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--proof-dir')
    options = parser.parse_args()
    if options.self_test:
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
    import pygame
    pygame.display.init()
    pygame.font.init()
    try:
        screen = pygame.display.set_mode((800, 500), pygame.RESIZABLE)
        pygame.display.set_caption('Mi juego · AURA Pygame')
        icon = pygame.Surface((32, 32), pygame.SRCALPHA)
        pygame.draw.circle(icon, '#53d9ee', (16, 16), 13)
        pygame.display.set_icon(icon)
        font = pygame.font.Font(None, 28)
        title = font.render('AURA · Pygame', True, '#53d9ee')
        instructions = font.render('Flechas / WASD: mover   Espacio: color   Esc: salir', True, '#e4eaf4')
        asset_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))/'assets'
        config = json.loads((asset_root/'game.json').read_text('utf-8'))
        position = pygame.Vector2(120, 220)
        original = position.copy()
        clock = pygame.time.Clock()
        running, frames, color_changes = True, 0, 0
        colors = config['player_colors']
        while running:
            dt = min(clock.tick(60)/1000.0, .05)
            if options.self_test and frames == 0:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
            if options.self_test and frames == 3:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_SPACE:
                        color_changes += 1
            keys = pygame.key.get_pressed()
            movement = pygame.Vector2(int(keys[pygame.K_RIGHT] or keys[pygame.K_d])-int(keys[pygame.K_LEFT] or keys[pygame.K_a]), int(keys[pygame.K_DOWN] or keys[pygame.K_s])-int(keys[pygame.K_UP] or keys[pygame.K_w]))
            if options.self_test:
                movement.x = 1
            if movement.length_squared():
                position += movement.normalize()*250*dt
            position.x = max(0, min(screen.get_width()-48, position.x))
            position.y = max(100, min(screen.get_height()-48, position.y))
            screen.fill(config['background'])
            screen.blit(title, (24, 20))
            screen.blit(instructions, (24, 58))
            pygame.draw.rect(screen, colors[color_changes % len(colors)], (round(position.x), round(position.y), 48, 48), border_radius=10)
            pygame.display.flip()
            frames += 1
        if options.self_test:
            proof = {'pygame_version': pygame.version.ver, 'sdl_version': pygame.get_sdl_version(), 'driver': pygame.display.get_driver(), 'frames': frames, 'position_changed': position.x > original.x, 'space_events': color_changes, 'assets_loaded': True, 'surface_size': screen.get_size()}
            assert proof['position_changed'] and color_changes == 1
            if options.proof_dir:
                folder = Path(options.proof_dir)
                folder.mkdir(parents=True, exist_ok=True)
                pygame.image.save(screen, str(folder/'pygame-surface.png'))
                (folder/'pygame-proof.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
            if sys.stdout:
                print(json.dumps(proof))
    finally:
        pygame.quit()


if __name__ == '__main__':
    main()
