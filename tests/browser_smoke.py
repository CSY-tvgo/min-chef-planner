"""Browser regressions: python3 tests/browser_smoke.py (requires Playwright + Chromium)."""
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
KEY = 'banquet-kitchen-plan-v1'

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def plan(page):
    return page.evaluate('(key) => JSON.parse(localStorage.getItem(key))', KEY)


def reset(page):
    page.evaluate('localStorage.clear()')
    page.reload()


def drag(page, locator, delta):
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y + delta, steps=8)
    page.mouse.up()
    assert not page.locator('#taskDialog').evaluate('(d) => d.open')


def scale(page):
    return page.locator('#planner').evaluate('(el) => parseFloat(el.style.getPropertyValue("--hour"))')


def set_range(page, start, end):
    page.locator('#setTimelineStart').click()
    page.locator('#timelineStart').fill(start)
    page.locator('#timelineEnd').fill(end)
    page.locator('#timelineForm button[type="submit"]').click()


def resize_column(page, delta):
    handle = page.locator('.column-resize').first
    handle.scroll_into_view_if_needed()
    box = handle.bounding_box()
    x, y = box['x'] + box['width']/2, box['y'] + box['height']/2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + delta, y, steps=8)
    page.mouse.up()


def open_step(page, task_id):
    page.locator('#manageMenu').click()
    dish_id = next(t for t in plan(page)['tasks'] if t['id'] == task_id)['dishId']
    page.locator(f'[data-open-dish="{dish_id}"]').click()
    page.locator(f'[data-edit-task="{task_id}"]').click()


def test_menu(browser, url, errors):
    context = browser.new_context(viewport={'width': 375, 'height': 812}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('dialog', lambda d: d.accept())
    page.goto(url)
    # Legacy plans migrate without losing task names, timing or completion.
    page.locator('.task-card .check').first.click()
    original = plan(page)
    legacy = dict(original)
    legacy.pop('dishes')
    legacy['tasks'] = [{k: v for k, v in task.items() if k != 'dishId'} for task in original['tasks']]
    page.evaluate('([k,v]) => localStorage.setItem(k, JSON.stringify(v))', [KEY, legacy])
    page.reload()
    page.locator('#manageMenu').click()
    assert page.locator('[data-open-dish]').count() == 5
    assert page.locator('[data-edit-task]').count() == 0
    page.locator('[data-open-dish]').first.click()
    assert page.locator('[data-edit-task]').count() == 2
    # A keyboard/viewport resize must not erase an unfinished name draft.
    page.locator('#dishName').fill('瑞典炖菜 <测试>')
    page.locator('#menuTitle').click()
    page.set_viewport_size({'width': 390, 'height': 700})
    assert page.locator('#dishName').input_value() == '瑞典炖菜 <测试>'
    page.locator('#dishForm button').click()
    dish_id = plan(page)['dishes'][0]['id']
    assert all(t['dish'] == '瑞典炖菜 <测试>' for t in plan(page)['tasks'] if t['dishId'] == dish_id)
    assert page.locator('#menuTitle').inner_text() == '瑞典炖菜 <测试>'
    assert [(t['start'], t['end'], t['done']) for t in original['tasks']] == [(t['start'], t['end'], t['done']) for t in plan(page)['tasks']]
    # A nested editor returns to the dish on Escape, cancel and save.
    page.locator('#addDishTask').click()
    assert page.locator('#taskDish').input_value() == dish_id
    assert page.locator('#taskStart').input_value() == '12:00'
    page.keyboard.press('Escape')
    assert page.locator('#menuDialog').evaluate('(d) => d.open')
    assert not page.locator('#taskDialog').evaluate('(d) => d.open')
    page.locator('#addDishTask').click()
    box = page.locator('#taskDialog').bounding_box()
    page.mouse.click(box['x'] + 3, box['y'] + 3)
    assert page.locator('#taskDialog').evaluate('(d) => d.open')
    page.locator('#taskStart').fill('13:00')
    page.locator('#taskEnd').fill('12:00')
    page.locator('#saveTask').click()
    assert page.locator('#taskError').inner_text()
    assert len(plan(page)['tasks']) == 8
    page.locator('#taskEnd').fill('13:30')
    page.locator('#saveTask').click()
    assert page.locator('[data-edit-task]').count() == 3
    new_task = plan(page)['tasks'][-1]
    assert new_task['dishId'] == dish_id
    assert new_task['appliances'] == []
    page.locator(f'[data-toggle-step="{new_task['id']}"]').click()
    assert plan(page)['tasks'][-1]['done']
    # Moving a step updates its association without duplicating or deleting it.
    page.locator(f'[data-edit-task="{new_task['id']}"]').click()
    other = plan(page)['dishes'][1]['id']
    page.locator('#taskDish').select_option(other)
    page.locator('#saveTask').click()
    assert plan(page)['tasks'][-1]['dishId'] == other
    assert page.locator('#dishName').input_value() == plan(page)['dishes'][1]['name']
    page.locator('#menuBack').click()
    # Empty and unnamed dishes are separate, persistent objects.
    for _ in range(2):
        page.locator('#addDish').click()
        assert page.locator('[data-edit-task]').count() == 0
        page.locator('#menuBack').click()
    assert len(plan(page)['dishes']) == 7
    page.reload()
    page.locator('#manageMenu').click()
    assert page.locator('[data-open-dish]').count() == 7
    page.locator('[data-open-dish]').last.click()
    page.locator('#deleteDish').click()
    assert len(plan(page)['dishes']) == 6
    assert len(plan(page)['tasks']) == 9
    page.locator(f'[data-open-dish="{dish_id}"]').click()
    page.locator('#deleteDish').click()
    assert all(t['dishId'] != dish_id for t in plan(page)['tasks'])
    assert len(plan(page)['tasks']) == 7
    page.locator('#menuDialog [data-close-dialog]').click()
    # Add tools at the end of the appliance headings; newly added tools scroll into view.
    last = page.locator('.appliance-head').last.bounding_box()
    add = page.locator('#addAppliance').bounding_box()
    assert add['x'] >= last['x'] + last['width']
    page.locator('#addAppliance').click()
    page.locator('#applianceName').fill('新蒸箱')
    page.locator('#applianceForm button[type="submit"]').click()
    assert page.locator('.appliance-head').last.inner_text().startswith('◉')
    new = page.locator('.appliance-head').last.bounding_box()
    wrap = page.locator('.planner-wrap').bounding_box()
    assert new['x'] + new['width'] <= wrap['x'] + wrap['width'] + 1
    page.set_viewport_size({'width': 1280, 'height': 1000})
    page.locator('#resetDemo').click()
    page.reload()
    page.locator('#manageMenu').click()
    assert page.locator('[data-open-dish]').count() == 5
    assert page.locator('.task-card').count() == 9
    assert not errors, errors
    context.close()
    print('PASS: dish-first menu, legacy migration, rename, empty/unnamed dishes, step ownership, nested dialogs, keyboard resize and trailing appliance control')


def run():
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
    Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as p:
            executable = os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium')
            browser = p.chromium.launch(executable_path=executable or None, headless=True, args=['--no-sandbox'])
            page = browser.new_page(viewport={'width': 1280, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            for asset in ('/', '/app.js', '/styles.css'):
                response = page.request.get(url + asset)
                assert response.ok and len(response.body()) > 100
            page.goto(url)
            assert page.title() == 'Min Chef（敏捷厨师）'
            assert page.locator('h1, h2').count() == 1
            assert page.locator('.appliance-head').count() == 4
            assert page.locator('.task-card').count() == 9
            assert page.locator('.timeline-corner').inner_text() == ''
            assert page.locator('.time-axis').bounding_box()['width'] == 28
            assert page.locator('.time-label').first.inner_text() == '10'
            wrap = page.locator('.planner-wrap').bounding_box()
            assert 2.4 < (wrap['height'] - 64) / scale(page) < 2.6
            widths = page.locator('.appliance-head').evaluate_all('(els) => els.map(e => e.getBoundingClientRect().width)')
            assert max(widths) - min(widths) < 1
            assert abs(widths[0] - (wrap['width'] - 30)/4) < 1
            resize_column(page, 60)
            assert abs(page.locator('.lane').first.bounding_box()['width'] - widths[0] - 60) < 1
            assert abs(page.locator('.lane').nth(1).bounding_box()['width'] - widths[1]) < 1
            resized_width = page.locator('.lane').first.bounding_box()['width']
            page.reload()
            assert abs(page.locator('.lane').first.bounding_box()['width'] - resized_width) < 1
            set_range(page, '10:15', '12:10')
            assert page.locator('.time-label').first.inner_text() == '11'
            body = page.locator('.timeline-body').bounding_box()
            for box in page.locator('.task-card').evaluate_all('(els) => els.map(e => {const r=e.getBoundingClientRect(); return {top:r.top,bottom:r.bottom};})'):
                assert box['top'] >= body['y'] - 1
                assert box['bottom'] <= body['y'] + body['height'] + 1
            assert page.locator('[data-id="t8"]').count() == 1
            set_range(page, '10:00', '22:00')
            # Simultaneous tasks remain individually visible and clickable.
            cards = page.locator('.lane').first.locator('.task-card[data-id="t6"], .task-card[data-id="t7"]')
            a, b = [cards.nth(i).bounding_box() for i in range(2)]
            assert a['x'] + a['width'] <= b['x'] or b['x'] + b['width'] <= a['x']
            # Blank names and multiple appliances, edit, completion and persistence.
            page.locator('#addTaskTop').click()
            page.locator('#taskStart').fill('19:00')
            page.locator('#taskEnd').fill('19:30')
            page.locator('#applianceChecks input').nth(0).check()
            page.locator('#applianceChecks input').nth(1).check()
            page.locator('#saveTask').click()
            data = plan(page)
            new_id = data['tasks'][-1]['id']
            assert data['tasks'][-1]['name'] == data['tasks'][-1]['dish'] == ''
            card = page.locator(f'.task-card[data-id="{new_id}"]').first
            assert card.is_visible()
            assert card.bounding_box()['y'] + card.bounding_box()['height'] <= page.locator('.timeline-body').bounding_box()['y'] + page.locator('.timeline-body').bounding_box()['height'] + 1
            card.locator('.check').click()
            page.reload()
            assert 'done' in page.locator(f'.task-card[data-id="{new_id}"]').first.get_attribute('class')
            page.locator('[data-filter="done"]').click()
            assert page.locator('.task-card').count() == 3
            page.locator('[data-filter="all"]').click()
            # Resize and move by five minutes; both appliance copies update.
            drag(page, page.locator(f'.task-card[data-id="{new_id}"] .resize-handle.bottom').first, -scale(page)/12)
            assert plan(page)['tasks'][-1]['end'] == '19:25'
            drag(page, page.locator(f'.task-card[data-id="{new_id}"] .move-handle').first, -scale(page)/12)
            assert (plan(page)['tasks'][-1]['start'], plan(page)['tasks'][-1]['end']) == ('18:55', '19:20')
            assert page.locator(f'.task-card[data-id="{new_id}"] small').all_text_contents() == ['18:55–19:20 · 未命名菜品'] * 2
            # Dragging against midnight still uses whole five-minute increments.
            drag(page, page.locator(f'.task-card[data-id="{new_id}"] .move-handle').first, scale(page)*8)
            assert (plan(page)['tasks'][-1]['start'], plan(page)['tasks'][-1]['end']) == ('23:30', '23:55')
            # Timeline changes don't remove earlier tasks from the menu.
            set_range(page, '20:00', '21:00')
            assert page.locator('.time-label').first.inner_text() == '20'
            assert page.locator(f'.task-card[data-id="{new_id}"]').count() == 0
            page.reload()
            assert plan(page)['timelineEnd'] == '21:00'
            set_range(page, '20:00', '19:00')
            assert page.locator('#timelineError').inner_text()
            assert page.locator('#timelineDialog').evaluate('(d) => d.open')
            page.locator('#timelineDialog [data-close-dialog]').first.click()
            open_step(page, new_id)
            page.locator('#taskName').fill('改名')
            page.locator('#saveTask').click()
            assert plan(page)['tasks'][-1]['name'] == '改名'
            assert page.locator('#menuDialog').evaluate('(d) => d.open')
            page.locator('#menuDialog [data-close-dialog]').click()
            # Removing every appliance keeps steps available, and blank appliances can be added.
            page.on('dialog', lambda d: d.accept())
            for _ in range(4):
                page.locator('.delete-appliance').first.click()
            assert len(plan(page)['appliances']) == 0
            open_step(page, new_id)
            page.locator('#deleteTask').click()
            assert len(plan(page)['tasks']) == 8
            page.locator('#menuDialog [data-close-dialog]').click()
            page.locator('#addAppliance').click()
            page.locator('#applianceForm button[type="submit"]').click()
            assert plan(page)['appliances'][0]['name'] == ''
            page.reload()
            assert page.locator('.appliance-head').count() == 1
            print('PASS: rendering, overlap layout, blank names, multiple appliances, CRUD, persistence, filtering, late steps and timeline')
            # Corrupt and unavailable storage must not crash or claim a successful save.
            for corrupt in ('{broken', '{}', '{"appliances":null,"tasks":[]}'):
                page.evaluate('([k,v]) => localStorage.setItem(k,v)', [KEY, corrupt])
                page.reload()
                assert page.locator('.task-card').count() == 9
                assert '无法读取缓存' in page.locator('#saveState').inner_text()
            reset(page)
            page.evaluate('() => { Storage.prototype.setItem = () => { throw new DOMException("full", "QuotaExceededError"); }; }')
            page.locator('.task-card .check').first.click()
            assert '保存失败' in page.locator('#saveState').inner_text()
            print('PASS: corrupt storage recovery and save failure reporting')
            # Mobile toolbar fits the viewport; real touch pointer drag doesn't scroll or open editor.
            context = browser.new_context(viewport={'width': 375, 'height': 812}, is_mobile=True, has_touch=True)
            mobile = context.new_page()
            mobile.on('pageerror', lambda error: errors.append(str(error)))
            mobile.goto(url)
            assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth')
            mobile.locator('#addAppliance').click()
            mobile.locator('#applianceDialog [data-close-dialog]').first.click()
            handle = mobile.locator('[data-id="t2"] .resize-handle.bottom').first
            handle.scroll_into_view_if_needed()
            box = handle.bounding_box()
            session = context.new_cdp_session(mobile)
            touch = {'x': box['x'] + box['width']/2, 'y': box['y'] + box['height']/2}
            session.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [touch]})
            touch['y'] += scale(mobile)/12
            session.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [touch]})
            session.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
            assert next(t for t in plan(mobile)['tasks'] if t['id'] == 't2')['end'] == '12:05'
            assert not mobile.locator('#taskDialog').evaluate('(d) => d.open')
            # Cancellation restores original duration and releases drag listeners.
            handle = mobile.locator('[data-id="t2"] .resize-handle.bottom').first
            box = handle.bounding_box()
            touch = {'x': box['x'] + box['width']/2, 'y': box['y'] + box['height']/2}
            session.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [touch]})
            touch['y'] += scale(mobile)/12
            session.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [touch]})
            session.send('Input.dispatchTouchEvent', {'type': 'touchCancel', 'touchPoints': []})
            assert next(t for t in plan(mobile)['tasks'] if t['id'] == 't2')['end'] == '12:05'
            # Column resizing also works with real touch, and only changes this appliance.
            column = mobile.locator('.column-resize').first
            column.scroll_into_view_if_needed()
            before = mobile.locator('.appliance-head').evaluate_all('(els) => els.map(e => e.getBoundingClientRect().width)')
            box = column.bounding_box()
            touch = {'x': box['x'] + box['width']/2, 'y': box['y'] + box['height']/2}
            session.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [touch]})
            touch['x'] += 20
            session.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [touch]})
            session.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
            after = mobile.locator('.appliance-head').evaluate_all('(els) => els.map(e => e.getBoundingClientRect().width)')
            assert abs(after[0] - before[0] - 20) < 1
            assert abs(after[1] - before[1]) < 1
            mobile.reload()
            assert abs(mobile.locator('.lane').first.bounding_box()['width'] - after[0]) < 1
            assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            context.close()
            test_menu(browser, url, errors)
            browser.close()
            print('PASS: mobile layout and real touch resizing; no JavaScript errors')
    finally:
        server.shutdown()
        server.server_close()

if __name__ == '__main__':
    run()
