# sources/human_behavior.py
import time
import random
import string

def random_sleep(min_s: float = 0.5, max_s: float = 2.0) -> None:
    time.sleep(random.uniform(min_s, max_s))

def micro_pause() -> None:
    time.sleep(random.uniform(0.1, 0.4))

def simulate_tab_switch_distraction(page) -> None:
    if random.random() < 0.2:
        print("  👀 [Human] Switched tabs... got distracted.")
        page.evaluate("window.dispatchEvent(new Event('blur'))")
        random_sleep(2.0, 7.0)
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        print("  👀 [Human] Back to the target tab.")

def idle_mouse_jiggle(page) -> None:
    current_x = random.randint(300, 800)
    current_y = random.randint(300, 600)
    for _ in range(random.randint(2, 5)):
        current_x += random.randint(-40, 40)
        current_y += random.randint(-40, 40)
        page.mouse.move(current_x, current_y, steps=random.randint(5, 10))
        time.sleep(random.uniform(0.05, 0.2))

def human_scroll(page) -> None:
    """Scroll down gradually like a human reading results."""
    steps = random.randint(3, 6)
    for _ in range(steps):
        scroll_amount = random.randint(200, 500)
        page.mouse.wheel(0, scroll_amount)
        random_sleep(0.3, 0.9)

    # 40% chance to scroll back up a bit
    if random.random() < 0.4:
        page.mouse.wheel(0, -random.randint(100, 300))
        random_sleep(0.2, 0.6)

def random_page_click(page) -> None:
    if random.random() < 0.25:
        x = random.randint(10, 50)
        y = random.randint(200, 600)
        page.mouse.click(x, y)
        micro_pause()
        if random.random() < 0.1:
            page.mouse.click(x, y)

def highlight_random_text(page) -> None:
    if random.random() < 0.3:
        paragraphs = page.query_selector_all('p, span')
        if paragraphs:
            el = random.choice(paragraphs)
            box = el.bounding_box()
            if box:
                page.mouse.move(box["x"], box["y"] + (box["height"] / 2))
                page.mouse.down()
                random_sleep(0.2, 0.5)
                page.mouse.move(box["x"] + (box["width"] / 2), box["y"] + (box["height"] / 2), steps=10)
                page.mouse.up()
                random_sleep(1.0, 2.0)
                page.mouse.click(10, 10)

def simulate_human_reading(page) -> None:
    """Master function combining the chaotic human behaviors."""
    simulate_tab_switch_distraction(page)
    random_sleep(0.5, 1.5)
    idle_mouse_jiggle(page)
    human_scroll(page)
    random_page_click(page)
    highlight_random_text(page)
    random_sleep(0.3, 1.0)