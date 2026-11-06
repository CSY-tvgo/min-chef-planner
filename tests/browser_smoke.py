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
    handle = page.locator('[data-resize-appliance]').first
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
    assert page.locator('.appliance-head').last.inner_text().startswith('🧰')
    new = page.locator('.appliance-head').last.bounding_box()
    wrap = page.locator('.planner-wrap').bounding_box()
    assert new['x'] + new['width'] <= wrap['x'] + wrap['width'] + 1
    page.set_viewport_size({'width': 1280, 'height': 1000})
    page.locator('#showHelp').click()
    assert page.locator('#helpDialog #resetDemo').inner_text() == '导入示例'
    page.locator('#resetDemo').click()
    page.reload()
    page.locator('#manageMenu').click()
    assert page.locator('[data-open-dish]').count() == 5
    assert page.locator('.task-card').count() == 9
    assert not errors, errors
    context.close()
    print('PASS: dish-first menu, legacy migration, rename, empty/unnamed dishes, step ownership, nested dialogs, keyboard resize and trailing appliance control')


def test_appliance_capacity(browser, url, errors):
    context = browser.new_context(viewport={'width': 375, 'height': 812}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(url)
    assert page.locator('.top-actions #manageMenu').count() == 1
    assert page.locator('#addTaskTop').count() == 0
    assert page.locator('#setTimelineStart').get_attribute('aria-label') == '设置时间范围'
    assert page.locator('#setTimelineStart').bounding_box()['y'] >= page.locator('.planner-wrap').bounding_box()['y'] + page.locator('.planner-wrap').bounding_box()['height']
    assert page.locator('#setTimelineStart').bounding_box()['y'] + 32 <= page.evaluate('innerHeight')
    assert page.locator('h1 span').inner_text() == '敏捷厨师（不是瑞典语的“我的老板”）'
    assert '我的老板' in page.locator('body').inner_text()
    page.locator('.task-card .check').first.click()
    data = plan(page)
    # Old steamer/stove symbols must migrate once, without swapping again on reload.
    old_icons = {'stove': '🔥', 'oven': '▱', 'steamer': '♨️'}
    data.pop('resourceIconVersion')
    for resource in data['appliances']:
        resource['icon'] = old_icons.get(resource['id'], resource['icon'])
    original_tasks = data['tasks']
    page.evaluate('([k,v]) => localStorage.setItem(k, JSON.stringify(v))', [KEY, data])
    page.reload()
    page.locator('.appliance-open').first.click()
    page.locator('#saveAppliance').click()
    data = plan(page)
    assert data['tasks'] == original_tasks
    expected = {'stove': '♨️', 'oven': '🔆', 'steamer': '🌫️'}
    assert all(a['icon'] == expected[a['id']] for a in data['appliances'] if a['id'] in expected)
    page.reload()
    assert all(a['icon'] == expected[a['id']] for a in plan(page)['appliances'] if a['id'] in expected)
    assert '排程会自动保存在当前浏览器的缓存中。' in page.locator('#helpDialog #saveState').inner_text()
    assert '已自动保存' not in page.locator('body').inner_text()
    tool = data['appliances'][0]
    template = data['tasks'][0]
    intervals = [('10:00', '10:30', 0), ('10:10', '10:40', 0), ('10:20', '10:30', 1), ('10:30', '10:50', 2), ('10:50', '11:00', 3)]
    data['tasks'] = [{**template, 'id': f'c{i}', 'start': start, 'end': end, 'dishId': data['dishes'][d]['id'], 'dish': data['dishes'][d]['name'], 'appliances': [tool['id']]} for i, (start, end, d) in enumerate(intervals)]
    page.evaluate('([k,v]) => localStorage.setItem(k, JSON.stringify(v))', [KEY, data])
    page.reload()
    assert page.locator('.capacity-conflict').count() == 0
    page.locator('.appliance-open').first.click()
    assert page.locator('#applianceCapacity').input_value() == '0'
    page.locator('#applianceName').fill('小蒸锅')
    page.locator('#applianceIcon').select_option('🍲')
    page.locator('#applianceCapacity').select_option('1')
    page.locator('#saveAppliance').click()
    assert page.locator('.capacity-conflict').count() == 4
    assert page.locator('[data-id="c4"]').get_attribute('class').find('capacity-conflict') < 0
    assert '4 个步骤' in page.locator('#capacityStatus').inner_text()
    page.reload()
    assert plan(page)['appliances'][0]['capacity'] == 1
    assert plan(page)['appliances'][0]['name'] == '小蒸锅'
    page.locator('.appliance-open').first.click()
    assert page.locator('#applianceIcon').input_value() == '🍲'
    page.locator('#applianceCapacity').select_option('2')
    page.locator('#saveAppliance').click()
    assert page.locator('.capacity-conflict').count() == 0
    # Four concurrent distinct dishes exceed every finite option.
    data = plan(page)
    data['tasks'] = [{**template, 'id': f'b{i}', 'start': '12:00', 'end': '12:30', 'dishId': data['dishes'][i]['id'], 'dish': data['dishes'][i]['name'], 'appliances': [tool['id']]} for i in range(4)]
    page.evaluate('([k,v]) => localStorage.setItem(k, JSON.stringify(v))', [KEY, data])
    page.reload()
    for limit in ('3', '2', '1', '0'):
        page.locator('.appliance-open').first.click()
        page.locator('#applianceCapacity').select_option(limit)
        page.locator('#saveAppliance').click()
        assert page.locator('.capacity-conflict').count() == (0 if limit == '0' else 4)
    page.locator('.appliance-open').first.focus()
    page.keyboard.press('Enter')
    assert page.locator('#applianceDialog').evaluate('(d) => d.open')
    page.locator('#applianceDialog [data-close-dialog]').first.click()
    # New tools default to unlimited, independent of the last edited tool.
    page.locator('#addAppliance').click()
    assert page.locator('#applianceId').input_value() == ''
    assert page.locator('#applianceCapacity').input_value() == '0'
    page.locator('#saveAppliance').click()
    assert plan(page)['appliances'][-1]['capacity'] == 0
    assert not errors, errors
    context.close()
    print('PASS: mobile menu/settings locations, appliance editing and capacity persistence, all limits, distinct dishes and exclusive interval endpoints')


def test_people(browser, url, errors):
    context = browser.new_context(viewport={'width': 375, 'height': 812}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('dialog', lambda d: d.accept())
    page.goto(url)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('#setTimelineStart').bounding_box()['y'] + 32 <= page.evaluate('innerHeight')
    page.locator('.task-card .check').first.click()
    open_step(page, 't1')
    assert page.locator('#peopleChecks input').count() == 0
    assert '添加' in page.locator('#peopleChecks').inner_text()
    page.locator('#saveTask').click()
    page.locator('#menuDialog [data-close-dialog]').click()
    people = []
    for name, icon in [('阿敏', '👨🏻‍🍳'), ('阿瑞', '👩🏻‍🍳')]:
        page.locator('#addAppliance').click()
        values = page.locator('#applianceIcon option').evaluate_all('(els) => els.map(e => e.value)')
        assert '⌁' not in values
        assert all(chef in values for chef in ['👨🏻‍🍳', '👩🏻‍🍳'])
        page.locator('#applianceIcon').select_option(icon)
        assert page.locator('#applianceNameLabel').inner_text() == '人员名称'
        assert page.locator('#saveAppliance').inner_text() == '添加人员'
        page.locator('#applianceName').fill(name)
        page.locator('#saveAppliance').click()
        people.append(plan(page)['appliances'][-1]['id'])
    assert '2' in page.locator('#summary').inner_text() and '位厨师' in page.locator('#summary').inner_text()
    open_step(page, 't1')
    assert page.locator('#applianceChecks input').count() == 4
    assert page.locator('#peopleChecks input').count() == 2
    assert page.locator('#peopleSelection').is_visible()
    for person in people:
        page.locator(f'#peopleChecks input[value="{person}"]').check()
    page.locator('#saveTask').click()
    page.locator('#menuDialog [data-close-dialog]').click()
    assert set(plan(page)['tasks'][0]['appliances']) == {'stove', *people}
    assert page.locator('[data-id="t1"]').count() == 3
    page.reload()
    open_step(page, 't1')
    assert page.locator('#peopleSelection').is_visible()
    assert page.locator('#peopleChecks input:checked').count() == 2
    assert page.locator('#applianceChecks input:checked').count() == 1
    page.locator(f'#peopleChecks input[value="{people[0]}"]').uncheck()
    page.locator('#saveTask').click()
    assert set(plan(page)['tasks'][0]['appliances']) == {'stove', people[1]}
    # A step may use just people, with no kitchen tools selected.
    page.locator('#addDishTask').click()
    assert page.locator('#peopleSelection').is_visible()
    page.locator(f'#peopleChecks input[value="{people[0]}"]').check()
    page.locator('#taskName').fill('切菜')
    page.locator('#saveTask').click()
    person_task = plan(page)['tasks'][-1]['id']
    assert plan(page)['tasks'][-1]['appliances'] == [people[0]]
    page.locator('#menuDialog [data-close-dialog]').click()
    assert page.locator(f'.lane [data-id="{person_task}"]').count() == 1
    # Changing a resource icon reclassifies it without discarding its assignments.
    page.locator(f'[data-open-appliance="{people[0]}"]').click()
    page.locator('#applianceIcon').select_option('🍲')
    page.locator('#saveAppliance').click()
    open_step(page, person_task)
    assert page.locator(f'#applianceChecks input[value="{people[0]}"]').is_checked()
    assert page.locator('#peopleChecks input').count() == 1
    page.locator('#saveTask').click()
    page.locator('#menuDialog [data-close-dialog]').click()
    # Removing a person detaches that person and preserves tool choices and tasks.
    page.locator(f'[data-open-appliance="{people[1]}"]').click()
    page.locator('#deleteAppliance').click()
    assert plan(page)['tasks'][0]['appliances'] == ['stove']
    assert len(plan(page)['tasks']) == 9
    # Editing an old icon must not re-add that icon to future Add dialogs.
    data = plan(page)
    data['appliances'][0]['icon'] = '⌁'
    page.evaluate('([k,v]) => localStorage.setItem(k, JSON.stringify(v))', [KEY, data])
    page.reload()
    page.locator('.appliance-open').first.click()
    assert page.locator('#applianceIcon').input_value() == '⌁'
    page.locator('#applianceDialog [data-close-dialog]').first.click()
    page.locator('#addAppliance').click()
    assert page.locator('#applianceIcon option[value="⌁"]').count() == 0
    assert not errors, errors
    context.close()
    print('PASS: visible joke, refreshed icons, optional multi-person assignments, reload, people-only steps, resource conversion/deletion and legacy icons')


def test_unassigned_and_links(browser, url, errors):
    context = browser.new_context(viewport={'width': 1280, 'height': 1000})
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(url)
    assert page.locator('#helpDialog #saveState').count() == 1
    assert page.locator('.page-notes').count() == 0
    assert page.locator('.top-actions #saveState').count() == 0
    page.locator('.task-card .check').first.click()
    data = plan(page)
    data['appliances'][0]['name'] = ''
    chef = { 'id': 'chef', 'name': '阿敏', 'icon': '👨🏻‍🍳', 'capacity': 0 }
    data['appliances'].append(chef)
    template = data['tasks'][0]
    stages = [
        ('a', '10:00', '10:20', ['stove'], False),
        ('b', '10:30', '11:00', ['stove', 'oven', 'chef'], True),
        ('c', '11:10', '11:30', ['rice'], False),
        ('d', '11:10', '11:30', ['steamer'], False),
        ('human', '11:40', '11:50', ['chef'], False),
        ('e', '12:00', '12:30', [], False),
        ('f', '12:30', '13:00', ['stove'], False),
    ]
    data['tasks'] = [{**template, 'id': id, 'name': id, 'start': start, 'end': end, 'appliances': tools, 'done': done} for id, start, end, tools, done in stages]
    page.evaluate('([k,v]) => localStorage.setItem(k, JSON.stringify(v))', [KEY, data])
    page.reload()
    assert page.locator('.unassigned-head').inner_text().startswith('无器具')
    assert page.locator('.lane[data-unassigned] .task-card').count() == 1
    assert page.locator('.lane[data-unassigned] [data-id="e"]').count() == 1
    assert page.locator('.lane[data-unassigned] [data-id="human"]').count() == 0
    header = page.locator('[data-open-appliance="stove"]')
    assert header.locator('strong, small').count() == 0
    assert '未命名' not in header.inner_text()
    assert header.locator('.tool-icon').evaluate('(e) => parseFloat(getComputedStyle(e).fontSize)') >= 25
    assert header.get_attribute('aria-label')
    paths = page.locator('.dish-connections path')
    assert paths.count() == 13
    assert page.locator('[data-from-id="a"][data-to-id="b"]').count() == 3
    assert page.locator('[data-from-id="b"][data-to-id="c"]').count() == 3
    assert page.locator('[data-from-id="b"][data-to-id="d"]').count() == 3
    assert page.locator('[data-from-id="c"][data-to-id="human"]').count() == 1
    assert page.locator('[data-from-id="d"][data-to-id="human"]').count() == 1
    assert page.locator('[data-from-id="human"][data-to-id="e"]').count() == 1
    assert page.locator('[data-from-id="c"][data-to-id="e"], [data-from-id="d"][data-to-id="e"]').count() == 0
    assert page.locator('.dish-connections').evaluate('(e) => getComputedStyle(e).pointerEvents') == 'none'
    assert 'NaN' not in page.locator('.dish-connections').inner_html()
    assert page.locator('[data-id="a"]').evaluate('(e) => e.style.background') == page.locator('[data-id="c"]').evaluate('(e) => e.style.background')
    old_path = page.locator('[data-from-id="a"][data-to-id="b"]').first.get_attribute('d')
    resize_column(page, 60)
    assert page.locator('[data-from-id="a"][data-to-id="b"]').first.get_attribute('d') != old_path
    old_path = page.locator('[data-from-id="a"][data-to-id="b"]').first.get_attribute('d')
    drag(page, page.locator('.lane[data-resource-id="stove"] [data-id="b"] .move-handle'), scale(page)/12)
    assert page.locator('[data-from-id="a"][data-to-id="b"]').first.get_attribute('d') != old_path
    page.locator('[data-filter="todo"]').click()
    assert page.locator('.dish-connections path').count() == 4
    assert page.locator('[data-from-id="a"][data-to-id="c"]').count() == 0
    page.locator('[data-filter="all"]').click()
    set_range(page, '10:35', '12:20')
    assert page.locator('.dish-connections path').count() == 9
    page.reload()
    assert page.locator('.dish-connections path').count() == 9
    # Empty-resource cards remain editable and draggable through the overlay.
    set_range(page, '10:00', '17:00')
    drag(page, page.locator('.lane[data-unassigned] [data-id="e"] .move-handle'), scale(page)/12)
    assert next(t for t in plan(page)['tasks'] if t['id'] == 'e')['start'] == '12:05'
    page.locator('.lane[data-unassigned] [data-id="e"] strong').click()
    assert page.locator('#applianceChecks input:checked, #peopleChecks input:checked').count() == 0
    assert page.locator('#peopleSelection').is_visible()
    assert page.locator('#peopleSelection summary').count() == 0
    assert page.locator('#applianceChecks').is_visible()
    page.locator('#taskDialog [data-close-dialog]').first.click()
    # Geometry recomputes on a mobile-size resize, without page-wide overflow.
    page.set_viewport_size({'width': 375, 'height': 812})
    page.wait_for_function('document.documentElement.scrollWidth <= innerWidth')
    assert 'NaN' not in page.locator('.dish-connections').inner_html()
    assert not errors, errors
    context.close()
    print('PASS: unassigned lane, icon-only unnamed headers, visible people choices, branching/merging resource curves, filtering, resizing and dragging')


def test_sequence_and_settings(browser, url, errors):
    context = browser.new_context(viewport={'width': 1280, 'height': 1000})
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(url)
    page.locator('.task-card .check').first.click()
    data = plan(page)
    template = data['tasks'][0]
    data['timelineStart'], data['timelineEnd'] = '16:00', '19:00'
    data['tasks'] = [{**template, 'id': id, 'name': name, 'start': start, 'end': end, 'appliances': [tool], 'done': False} for id, name, start, end, tool in [
        ('marinate', '腌制排骨', '15:30', '17:00', 'stove'),
        ('tray', '放在烤盘里', '17:05', '18:05', 'steamer'),
        ('roast', '烤制排骨', '17:15', '17:50', 'oven')]]
    page.evaluate('([k,v]) => localStorage.setItem(k, JSON.stringify(v))', [KEY, data])
    page.reload()
    assert page.locator('[data-from-id="marinate"][data-to-id="roast"]').count() == 1
    assert page.locator('[data-from-id="marinate"][data-to-id="tray"]').count() == 1
    assert page.locator('[data-from-id="tray"][data-to-id="roast"]').count() == 0
    old_scale = scale(page)
    page.locator('#setTimelineStart').click()
    page.locator('#timelineScale').select_option('1')
    page.locator('#timelineStep').select_option('15')
    page.locator('#timelineForm button[type="submit"]').click()
    assert abs(scale(page) / old_scale - 2.5) < .01
    drag(page, page.locator('[data-id="roast"] .move-handle'), scale(page)/12)
    assert next(t for t in plan(page)['tasks'] if t['id'] == 'roast')['start'] == '17:15'
    drag(page, page.locator('[data-id="roast"] .move-handle'), scale(page)/4)
    assert next(t for t in plan(page)['tasks'] if t['id'] == 'roast')['start'] == '17:30'
    page.reload()
    assert plan(page)['visibleHours'] == 1 and plan(page)['dragStep'] == 15
    assert page.locator('[data-from-id="marinate"][data-to-id="roast"]').count() == 1
    # Column order is independent from the resource IDs used by each step.
    before = plan(page)
    handle = page.locator('.column-move').first
    handle.scroll_into_view_if_needed()
    source, target = handle.bounding_box(), page.locator('.appliance-head').nth(1).bounding_box()
    x, y = source['x'] + source['width']/2, source['y'] + source['height']/2
    page.mouse.move(x, y); page.mouse.down()
    page.mouse.move(target['x'] + target['width']*.75, y, steps=8); page.mouse.up()
    after = plan(page)
    assert [a['id'] for a in after['appliances']][:2] == [a['id'] for a in before['appliances']][:2][::-1]
    assert after['tasks'] == before['tasks']
    assert not page.locator('#applianceDialog').evaluate('(d) => d.open')
    page.reload()
    assert [a['id'] for a in plan(page)['appliances']] == [a['id'] for a in after['appliances']]
    # Escape cancels an in-progress reorder.
    handle = page.locator('.column-move').first
    box = handle.bounding_box()
    page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
    page.mouse.down(); page.mouse.move(box['x'] + 400, box['y'] + box['height']/2, steps=8)
    page.keyboard.press('Escape'); page.mouse.up()
    assert plan(page)['appliances'] == after['appliances']
    page.locator('.column-move').first.focus(); page.keyboard.press('ArrowRight')
    assert [a['id'] for a in plan(page)['appliances']][:2] == [a['id'] for a in before['appliances']][:2]
    assert page.locator('.unassigned-head').count() == 0
    assert not errors, errors
    context.close()
    # Real mobile touch reorders columns without opening their settings.
    context = browser.new_context(viewport={'width': 375, 'height': 812}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(url)
    page.locator('.task-card .check').first.click()
    order = [a['id'] for a in plan(page)['appliances']]
    handle = page.locator('.column-move').first
    box, target = handle.bounding_box(), page.locator('.appliance-head').nth(1).bounding_box()
    touch = {'x': box['x']+box['width']/2, 'y': box['y']+box['height']/2}
    session = context.new_cdp_session(page)
    session.send('Input.dispatchTouchEvent', {'type':'touchStart','touchPoints':[touch]})
    touch['x'] = target['x']+target['width']*.75
    session.send('Input.dispatchTouchEvent', {'type':'touchMove','touchPoints':[touch]})
    session.send('Input.dispatchTouchEvent', {'type':'touchEnd','touchPoints':[]})
    assert [a['id'] for a in plan(page)['appliances']][:2] == order[:2][::-1]
    assert not page.locator('#applianceDialog').evaluate('(d) => d.open')
    # Holding near the mobile edge scrolls across columns; touch cancellation restores order.
    data = plan(page)
    data['appliances'].extend([{**data['appliances'][0], 'id': f'extra{i}'} for i in range(4)])
    page.evaluate('([k,v]) => localStorage.setItem(k, JSON.stringify(v))', [KEY, data])
    page.reload()
    order = [a['id'] for a in plan(page)['appliances']]
    box = page.locator('.column-move').first.bounding_box()
    wrap = page.locator('.planner-wrap').bounding_box()
    touch = {'x':box['x']+box['width']/2,'y':box['y']+box['height']/2}
    session.send('Input.dispatchTouchEvent', {'type':'touchStart','touchPoints':[touch]})
    touch['x'] = wrap['x']+wrap['width']-6
    session.send('Input.dispatchTouchEvent', {'type':'touchMove','touchPoints':[touch]})
    page.wait_for_function('document.querySelector(".planner-wrap").scrollLeft > 40')
    page.wait_for_function('(id) => state.appliances.findIndex(a => a.id === id) > 1', arg=order[0])
    session.send('Input.dispatchTouchEvent', {'type':'touchCancel','touchPoints':[]})
    assert [a['id'] for a in plan(page)['appliances']] == order
    assert not errors, errors
    context.close()
    print('PASS: screenshot regression, finished predecessors only, custom scale/step, desktop/touch/keyboard column order and cancellation')


def semantic_plan(data):
    resources = {a['id']: i for i, a in enumerate(data['appliances'])}
    dishes = {d['id']: i for i, d in enumerate(data['dishes'])}
    return {
        'range': [data['timelineStart'], data['timelineEnd']],
        'scale': data.get('visibleHours', 2.5), 'step': data.get('dragStep', 5),
        'unassigned_width': data.get('unassignedWidth', 0),
        'resources': [[a['name'], a['icon'], a.get('width', 0), a.get('capacity', 0)] for a in data['appliances']],
        'dishes': [d['name'] for d in data['dishes']],
        'tasks': [[t['name'], dishes[t['dishId']], t['start'], t['end'], [resources[id] for id in t['appliances']], t['note'], t['done'], t.get('timingMode', 'fixed'), t.get('duration', 0) if t.get('timingMode') == 'duration' else 0, t.get('scheduled', True)] for t in data['tasks']]
    }


def test_transfer(browser, url, errors):
    context = browser.new_context(permissions=['clipboard-read', 'clipboard-write'])
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(url)
    page.locator('.task-card .check').first.click()
    source = plan(page)
    source['visibleHours'], source['dragStep'] = 3, 10
    source['unassignedWidth'] = 177
    source['appliances'].reverse()
    source['appliances'][0]['width'], source['appliances'][0]['capacity'] = 193, 2
    source['appliances'].append({'id':'chef','name':'小敏👩🏻‍🍳','icon':'👩🏻‍🍳','capacity':1})
    source['tasks'][0]['appliances'].append('chef')
    source['tasks'][0]['note'] = '中文、瑞典语 köttbullar、emoji 🍲 和 <文字>'
    source['tasks'][1]['appliances'] = []
    source['dishes'].extend([{'id':'empty1','name':''},{'id':'empty2','name':''}])
    page.evaluate('([k,v]) => localStorage.setItem(k, JSON.stringify(v))', [KEY, source])
    page.reload(); page.locator('#manageMenu').click(); page.locator('#openTransfer').click()
    page.locator('#exportPlan').click()
    page.wait_for_function('document.querySelector("#exportText").value.startsWith("MC1.")')
    token = page.locator('#exportText').input_value()
    page.wait_for_function('!document.querySelector("#exportPlan").disabled')
    assert page.evaluate('navigator.clipboard.readText()') == token
    assert len(token) < len(json.dumps(source, ensure_ascii=False).encode()) / 2
    # Clipboard denial leaves a selectable text fallback.
    page.evaluate('() => { navigator.clipboard.writeText = async () => { throw new Error("Denied"); }; document.execCommand = () => false; }')
    page.locator('#exportPlan').click()
    page.wait_for_function('!document.querySelector("#exportPlan").disabled')
    assert '请长按' in page.locator('#transferStatus').inner_text()
    assert page.locator('#exportText').input_value() == token
    other = browser.new_context()
    dest = other.new_page()
    dest.on('pageerror', lambda e: errors.append(str(e)))
    dest.goto(url); dest.locator('.task-card .check').first.click()
    before = plan(dest)
    dest.locator('#manageMenu').click(); dest.locator('#openTransfer').click()
    # Wrapped text from messaging apps remains importable; preview never commits it.
    dest.locator('#importText').fill(token[:20]+'\n'+token[20:])
    dest.locator('#previewImport').click()
    dest.locator('#confirmImport').wait_for(state='visible')
    assert plan(dest) == before
    assert '尚未替换' in dest.locator('#transferStatus').inner_text()
    dest.locator('#importText').fill('MC1.broken')
    assert dest.locator('#confirmImport').is_hidden()
    dest.locator('#previewImport').click()
    dest.wait_for_function('!document.querySelector("#previewImport").disabled')
    assert '无效' in dest.locator('#transferStatus').inner_text()
    assert plan(dest) == before
    # Reject valid gzip with invalid references and oversized decompressed content.
    import gzip, base64
    bad_payload = [1,600,1020,2.5,5,[],[],[['坏步骤',9,600,630,[],'',0]]]
    bad_token = 'MC1.' + base64.urlsafe_b64encode(gzip.compress(json.dumps(bad_payload).encode())).decode().rstrip('=')
    bomb = 'MC1.' + base64.urlsafe_b64encode(gzip.compress(b'A'*1048577)).decode().rstrip('=')
    corrupted = bytearray(base64.urlsafe_b64decode(token[4:]+'='*((4-len(token[4:])%4)%4)))
    corrupted[-8] ^= 1
    bad_crc = 'MC1.' + base64.urlsafe_b64encode(corrupted).decode().rstrip('=')
    for invalid in [bad_token, bomb, token[:-8], bad_crc]:
        dest.locator('#importText').fill(invalid); dest.locator('#previewImport').click()
        dest.wait_for_function('!document.querySelector("#previewImport").disabled')
        assert dest.locator('#confirmImport').is_hidden()
        assert plan(dest) == before
    dest.locator('#importText').fill(token); dest.locator('#previewImport').click()
    dest.locator('#confirmImport').wait_for(state='visible')
    dest.evaluate('() => { window.originalSet = Storage.prototype.setItem; Storage.prototype.setItem = () => { throw new Error("Quota"); }; }')
    dest.locator('#confirmImport').click()
    assert '原排程未改动' in dest.locator('#transferStatus').inner_text()
    assert plan(dest) == before
    dest.evaluate('() => { Storage.prototype.setItem = window.originalSet; }')
    dest.locator('#confirmImport').click()
    assert semantic_plan(plan(dest)) == semantic_plan(source)
    dest.reload()
    assert semantic_plan(plan(dest)) == semantic_plan(source)
    # Previously exported version-1 texts still load with default unassigned width.
    old_payload = json.loads(gzip.decompress(base64.urlsafe_b64decode(token[4:]+'='*((4-len(token[4:])%4)%4))))
    old_payload[0] = 1
    old_payload[7] = [task[:7] for task in old_payload[7]]
    old_payload = old_payload[:8]
    legacy_token = 'MC1.' + base64.urlsafe_b64encode(gzip.compress(json.dumps(old_payload).encode())).decode().rstrip('=')
    dest.locator('#manageMenu').click(); dest.locator('#openTransfer').click()
    dest.locator('#importText').fill(legacy_token); dest.locator('#previewImport').click()
    dest.locator('#confirmImport').wait_for(state='visible'); dest.locator('#confirmImport').click()
    legacy_expected = semantic_plan(source); legacy_expected['unassigned_width'] = 0
    assert semantic_plan(plan(dest)) == legacy_expected
    assert not errors, errors
    other.close(); context.close()
    print(f'PASS: compressed text ({len(token)} chars), clipboard/fallback, cross-device restore, Unicode, invalid/oversized imports, preview and storage failure safety')


def test_mobile_compatibility(browser, url, errors):
    import hashlib, re
    context = browser.new_context(viewport={'width': 375, 'height': 812}, is_mobile=True, has_touch=True)
    # Reproduce a device without native compression or the modern clipboard API.
    context.add_init_script('''
        window.CompressionStream = undefined;
        window.DecompressionStream = undefined;
        Object.defineProperty(navigator, 'clipboard', { get: () => undefined });
        document.execCommand = () => false;
    ''')
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    # Old cached unversioned resources must never be requested by the new page.
    page.route(re.compile(r'/app\.js$'), lambda route: route.fulfill(body='window.oldCachedScript = true;', content_type='application/javascript'))
    page.route(re.compile(r'/styles\.css$'), lambda route: route.fulfill(body='.column-move { pointer-events:none; }', content_type='text/css'))
    page.goto(url)
    assert page.locator('.task-card').count() == 9
    for name in ['app.js', 'styles.css', 'vendor/fflate-0.8.2.min.js']:
        expected = name + '?v=' + hashlib.sha256((ROOT / name).read_bytes()).hexdigest()[:12]
        assert page.locator(f'[src^="{name}"], [href^="{name}"]').evaluate('(e) => e.getAttribute("src") || e.getAttribute("href")') == expected
    assert page.evaluate('typeof CompressionStream') == 'undefined'
    # Real taps still open settings, while dragging the whole header sorts columns.
    page.locator('.appliance-open').first.tap()
    assert page.locator('#applianceDialog').evaluate('(d) => d.open')
    assert page.locator('#moveResourceLeft').is_disabled()
    page.locator('#moveResourceRight').tap()
    assert page.locator('#moveResourceLeft').is_enabled()
    page.locator('#moveResourceLeft').tap()
    page.locator('#applianceDialog [data-close-dialog]').first.tap()
    order = [a['id'] for a in plan(page)['appliances']]
    source = page.locator('.appliance-open').first.bounding_box()
    target = page.locator('.appliance-open').nth(1).bounding_box()
    touch = {'x':source['x']+source['width']/2,'y':source['y']+44}
    session = context.new_cdp_session(page)
    session.send('Input.dispatchTouchEvent', {'type':'touchStart','touchPoints':[touch]})
    touch['x'] = target['x']+target['width']*.75
    touch['y'] += 3
    session.send('Input.dispatchTouchEvent', {'type':'touchMove','touchPoints':[touch]})
    session.send('Input.dispatchTouchEvent', {'type':'touchEnd','touchPoints':[]})
    assert [a['id'] for a in plan(page)['appliances']][:2] == order[:2][::-1]
    assert not page.locator('#applianceDialog').evaluate('(d) => d.open')
    page.locator('#setTimelineStart').tap()
    page.locator('#timelineScale').select_option('2')
    page.locator('#timelineStep').select_option('15')
    page.locator('#timelineForm button[type="submit"]').tap()
    page.reload()
    assert plan(page)['visibleHours'] == 2 and plan(page)['dragStep'] == 15
    handle = page.locator('[data-id="t2"] .resize-handle.bottom')
    handle.scroll_into_view_if_needed()
    box = handle.bounding_box()
    touch = {'x':box['x']+box['width']/2,'y':box['y']+box['height']/2}
    session.send('Input.dispatchTouchEvent', {'type':'touchStart','touchPoints':[touch]})
    touch['y'] += scale(page)/4
    session.send('Input.dispatchTouchEvent', {'type':'touchMove','touchPoints':[touch]})
    session.send('Input.dispatchTouchEvent', {'type':'touchEnd','touchPoints':[]})
    assert next(t for t in plan(page)['tasks'] if t['id']=='t2')['end'] == '12:15'
    # Keep failed persistence visible in the settings dialog instead of closing silently.
    page.evaluate('() => { window.savedSet = Storage.prototype.setItem; Storage.prototype.setItem = () => { throw new Error("Quota"); }; }')
    page.locator('#setTimelineStart').tap()
    page.locator('#timelineScale').select_option('3')
    page.locator('#timelineForm button[type="submit"]').tap()
    assert page.locator('#timelineDialog').evaluate('(d) => d.open')
    assert '缓存保存失败' in page.locator('#timelineError').inner_text()
    page.evaluate('() => { Storage.prototype.setItem = window.savedSet; }')
    page.locator('#timelineForm button[type="submit"]').tap()
    assert plan(page)['visibleHours']==3
    page.locator('#manageMenu').tap(); page.locator('#openTransfer').tap()
    page.locator('#exportPlan').tap()
    page.wait_for_function('!document.querySelector("#exportPlan").disabled')
    token = page.locator('#exportText').input_value()
    assert token.startswith('MC1.')
    assert '请长按' in page.locator('#transferStatus').inner_text()
    assert page.locator('#copyExport').is_enabled()
    page.locator('#copyExport').tap()
    assert page.locator('#exportText').evaluate('(e) => e.selectionEnd-e.selectionStart') == len(token)
    page.locator('#importText').fill(token)
    page.locator('#previewImport').tap()
    page.locator('#confirmImport').wait_for(state='visible')
    before = semantic_plan(plan(page))
    page.locator('#confirmImport').tap()
    assert semantic_plan(plan(page)) == before
    # Finger taps execute mutating actions once, including quickly repeated taps.
    count = len(plan(page)['dishes'])
    page.locator('#manageMenu').tap(); page.locator('#addDish').tap()
    assert len(plan(page)['dishes']) == count + 1
    page.locator('#menuBack').tap(); page.locator('#addDish').tap()
    assert len(plan(page)['dishes']) == count + 2
    page.locator('#menuBack').tap(); page.locator('[data-open-dish]').first.tap()
    task_id = page.locator('[data-toggle-step]').first.get_attribute('data-toggle-step')
    done = next(t for t in plan(page)['tasks'] if t['id']==task_id)['done']
    page.locator('[data-toggle-step]').first.tap()
    assert next(t for t in plan(page)['tasks'] if t['id']==task_id)['done'] != done
    page.locator('[data-edit-task]').first.tap()
    page.wait_for_timeout(350)  # Let any delayed native compatibility click arrive.
    assert page.locator('#taskDialog').evaluate('(d) => d.open')
    checkbox = page.locator('#applianceChecks input').first
    checked = checkbox.is_checked()
    checkbox.tap()
    assert checkbox.is_checked() != checked
    page.locator('#taskDialog [data-close-dialog]').first.tap()
    assert page.locator('#menuDialog').evaluate('(d) => d.open')
    assert not errors, errors
    context.close()
    print('PASS: cached old assets, missing compression/clipboard APIs, whole-header mobile drag/tap, persisted settings, real touch step and visible storage errors')


def test_completion_links_and_compact_layout(browser, url, errors):
    context = browser.new_context(viewport={'width': 1200, 'height': 900})
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(url); page.locator('.task-card .check').first.click()
    data = plan(page)
    template = data['tasks'][0]
    data['timelineStart'], data['timelineEnd'] = '16:00', '19:00'
    data['appliances'] = sorted(data['appliances'], key=lambda a: ['stove','steamer','oven','rice'].index(a['id']))
    names = {'stove':'腌制碗','steamer':'烤盘','oven':'烤箱','rice':'上菜盘'}
    for a in data['appliances']:
        a['width'] = 150
        a['name'] = names[a['id']]
    data['tasks'] = [{**template, 'id': id, 'name': name, 'start': start, 'end': end, 'appliances': [tool], 'done': False} for id, name, start, end, tool in [
        ('prep','腌制排骨','16:20','16:50','stove'),
        ('tray','放在烤盘里','17:06','18:06','steamer'),
        ('roast','烤制排骨','17:13','17:56','oven'),
        ('serve','上菜','18:06','18:45','rice')]]
    page.evaluate('([k,v]) => localStorage.setItem(k, JSON.stringify(v))', [KEY, data]); page.reload()
    path = page.locator('path[data-kind="completion"][data-from-id="roast"][data-to-id="tray"]')
    assert path.count() == 1
    assert page.locator('path[data-kind="sequence"][data-from-id="prep"][data-to-id="roast"]').count() == 1
    assert page.locator('path[data-kind="sequence"][data-from-id="tray"][data-to-id="roast"]').count() == 0
    assert page.locator('path[data-kind="sequence"][data-from-id="tray"][data-to-id="serve"]').count() == 1
    endpoints = path.evaluate('(p) => { const a=p.getPointAtLength(0), b=p.getPointAtLength(p.getTotalLength()); return [a.y,b.y]; }')
    top = page.locator('#lanes').bounding_box()['y']
    for y, id in zip(endpoints, ['roast','tray']):
        box = page.locator(f'.task-card[data-id="{id}"]').bounding_box()
        assert abs(y - (box['y'] + box['height'] - top)) < .1
    # A clipped parent end is not a real end and must not get an artificial join.
    set_range(page, '16:00', '18:00')
    assert path.count() == 0
    set_range(page, '16:00', '19:00')
    assert path.count() == 1
    page.screenshot(path='/tmp/minchef-completion-desktop.png')
    # Nested intervals only join to their immediate parent; filtering cannot skip it.
    data = plan(page)
    data['tasks'].append({**data['tasks'][0], 'id':'nested', 'name':'检查熟度', 'start':'17:20','end':'17:40','appliances':['rice']})
    data['tasks'].append({**data['tasks'][0], 'id':'other','dishId':data['dishes'][1]['id'],'dish':data['dishes'][1]['name'],'start':'16:00','end':'19:00','appliances':['stove']})
    page.evaluate('([k,v]) => localStorage.setItem(k, JSON.stringify(v))', [KEY, data]); page.reload()
    assert page.locator('path[data-kind="completion"][data-from-id="nested"][data-to-id="roast"]').count() == 1
    assert page.locator('path[data-kind="completion"][data-from-id="nested"][data-to-id="tray"]').count() == 0
    assert page.locator('path[data-kind="completion"][data-to-id="other"]').count() == 0
    data['tasks'][2]['done'] = True
    page.evaluate('([k,v]) => localStorage.setItem(k, JSON.stringify(v))', [KEY, data]); page.reload()
    page.locator('[data-filter="todo"]').click()
    assert page.locator('path[data-kind="completion"][data-from-id="nested"]').count() == 0
    assert not errors, errors
    context.close()
    context = browser.new_context(viewport={'width':375,'height':812}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(url); page.locator('.task-card .check').first.tap()
    data = plan(page)
    data['appliances'].append({'id':'chef','name':'小敏','icon':'👩🏻‍🍳','capacity':1})
    page.evaluate('([k,v]) => localStorage.setItem(k, JSON.stringify(v))', [KEY, data]); page.reload()
    for width, height in [(375,812),(360,640),(320,568)]:
        page.set_viewport_size({'width':width,'height':height})
        page.wait_for_function('document.documentElement.scrollHeight <= innerHeight + 2 && document.documentElement.scrollWidth <= innerWidth')
        assert page.locator('.summary').bounding_box()['height'] <= 27
        assert page.locator('.summary .stat').count() == 4
        assert page.locator('.summary strong').first.evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)') <= 17
        assert page.locator('.timeline-footer').bounding_box()['y'] + page.locator('.timeline-footer').bounding_box()['height'] <= height
        assert page.locator('.planner-wrap').bounding_box()['height'] >= 180
    page.set_viewport_size({'width':375,'height':812})
    page.wait_for_function('innerWidth===375 && document.documentElement.scrollHeight<=innerHeight+2')
    page.screenshot(path='/tmp/minchef-compact-mobile.png')
    # Error notices are also included in the first-screen layout budget.
    page.evaluate('() => { Storage.prototype.setItem = () => { throw new Error("Quota"); }; }')
    page.locator('.task-card .check').first.tap()
    assert '保存失败' in page.locator('#saveState').inner_text()
    assert page.evaluate('document.documentElement.scrollHeight <= innerHeight + 2')
    assert not errors, errors
    context.close()
    print('PASS: screenshot bottom-to-bottom join, nested parents, clipping/filtering, compact four-stat overview and full portrait first screen including errors')


def seed_unassigned(page):
    page.locator('.task-card .check').first.click()
    data = plan(page)
    data['tasks'].append({**data['tasks'][0], 'id':'unassigned-fixture', 'name':'备料', 'start':'10:00', 'end':'10:15', 'appliances':[], 'done':False})
    page.evaluate('([k,v]) => localStorage.setItem(k,JSON.stringify(v))',[KEY,data])
    page.reload()


def test_unassigned_width_and_help(browser, url, errors):
    context = browser.new_context(viewport={'width':1280,'height':1000})
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(url)
    seed_unassigned(page)
    assert page.locator('.unassigned-head [data-move-appliance], .unassigned-head .appliance-open').count()==0
    original_width = page.locator('.unassigned-head').bounding_box()['width']
    resource_widths = page.locator('.appliance-head').evaluate_all('(els)=>els.map(e=>e.getBoundingClientRect().width)')
    handle = page.locator('[data-resize-unassigned]')
    box = handle.bounding_box()
    page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2); page.mouse.down()
    page.mouse.move(box['x']+box['width']/2+55,box['y']+box['height']/2,steps=8); page.mouse.up()
    assert abs(plan(page)['unassignedWidth']-original_width-55)<1
    assert page.locator('.appliance-head').evaluate_all('(els)=>els.map(e=>e.getBoundingClientRect().width)')==resource_widths
    assert abs(page.locator('.lane[data-unassigned]').bounding_box()['width']-plan(page)['unassignedWidth'])<1
    saved_width=plan(page)['unassignedWidth']
    page.reload()
    assert abs(page.locator('.unassigned-head').bounding_box()['width']-saved_width)<1
    page.locator('[data-resize-unassigned]').focus()
    page.keyboard.press('ArrowRight'); page.keyboard.press('ArrowRight')
    assert abs(plan(page)['unassignedWidth']-saved_width-20)<1
    order=[a['id'] for a in plan(page)['appliances']]
    title=page.locator('.unassigned-head strong').bounding_box()
    page.mouse.move(title['x']+20,title['y']+5); page.mouse.down()
    page.mouse.move(title['x']+200,title['y']+5,steps=8); page.mouse.up()
    assert [a['id'] for a in plan(page)['appliances']]==order
    assert page.locator('.unassigned-head').evaluate('(e)=>e.parentElement.firstElementChild===e')
    # Reordering a real resource still cannot move it before the fixed column.
    page.locator('.column-move').first.focus(); page.keyboard.press('ArrowRight')
    assert page.locator('.unassigned-head').evaluate('(e)=>e.parentElement.firstElementChild===e')
    assert abs(page.locator('.unassigned-head').bounding_box()['width']-saved_width-20)<1
    context.close()
    context=browser.new_context(viewport={'width':375,'height':812},is_mobile=True,has_touch=True)
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(url)
    seed_unassigned(page)
    session=context.new_cdp_session(page)
    def touch_resize(delta, cancel=False):
        box=page.locator('[data-resize-unassigned]').bounding_box()
        touch={'x':box['x']+box['width']/2,'y':box['y']+box['height']/2}
        session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[touch]})
        touch['x']+=delta
        session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[touch]})
        session.send('Input.dispatchTouchEvent',{'type':'touchCancel' if cancel else 'touchEnd','touchPoints':[]})
    width=page.locator('.unassigned-head').bounding_box()['width']
    touch_resize(30,True)
    assert abs(page.locator('.unassigned-head').bounding_box()['width']-width)<1
    assert 'unassignedWidth' not in plan(page)
    touch_resize(35)
    assert abs(plan(page)['unassignedWidth']-width-35)<1
    page.reload()
    assert abs(page.locator('.lane[data-unassigned]').bounding_box()['width']-width-35)<1
    page.locator('[data-resize-unassigned]').focus()
    for _ in range(10): page.keyboard.press('ArrowLeft')
    assert plan(page)['unassignedWidth']==64
    assert page.locator('.page-notes').count()==0
    assert '排程会自动保存' not in page.locator('body').inner_text()
    gear=page.locator('#setTimelineStart').bounding_box();help=page.locator('#showHelp').bounding_box()
    assert abs(gear['y']+gear['height']/2-help['y']-help['height']/2)<1
    assert help['x']>gear['x'] and help['x']+help['width']>=page.evaluate('innerWidth')-15
    page.locator('#showHelp').tap()
    page.wait_for_timeout(350)  # A delayed touch click must not close the new dialog.
    assert page.locator('#helpDialog').evaluate('(d)=>d.open')
    instructions=page.locator('#helpDialog .help-list').inner_text()
    assert all(word in instructions for word in ['菜单','自动排程','列宽','时长','无器具','步进','曲线'])
    assert len(instructions)<400
    assert '自动保存' in page.locator('#saveState').inner_text()
    page.screenshot(path='/tmp/minchef-help-dialog.png')
    page.locator('#helpDialog [data-close-dialog]').tap()
    assert not page.locator('#helpDialog').evaluate('(d)=>d.open')
    page.screenshot(path='/tmp/minchef-help-footer.png')
    page.evaluate('() => { Storage.prototype.setItem = () => { throw new Error("Quota"); }; }')
    page.locator('.task-card .check').first.tap()
    assert page.locator('#saveAlert').is_visible()
    assert '保存失败' in page.locator('#saveAlert').inner_text()
    assert page.evaluate('document.documentElement.scrollHeight<=innerHeight+2')
    assert not errors,errors
    context.close()
    print('PASS: fixed unassigned column width via mouse/touch/keyboard, cancellation, persistence, help-only instructions and visible save errors')


def test_multi_tool_links_and_example(browser, url, errors):
    context=browser.new_context(viewport={'width':1100,'height':900})
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(url);page.locator('.task-card .check').first.click()
    base=plan(page);template=base['tasks'][0]
    def seed(stages):
        data={**base,'timelineStart':'10:00','timelineEnd':'13:00','tasks':[
            {**template,'id':id,'name':name,'start':start,'end':end,'appliances':tools,'done':False}
            for id,name,start,end,tools in stages]}
        page.evaluate('([k,v])=>localStorage.setItem(k,JSON.stringify(v))',[KEY,data]);page.reload()
    seed([('a','','10:00','11:00',['stove','oven']),('b',' ','11:00','11:30',['stove','oven'])])
    assert page.locator('[data-id="a"] strong').all_text_contents()==[template['dish']]*2
    assert page.locator('[data-id="b"] strong').all_text_contents()==[template['dish']]*2
    assert '未命名步骤' not in page.locator('[data-id="a"]').first.get_attribute('title')
    paths=page.locator('path[data-kind="sequence"][data-from-id="a"][data-to-id="b"]')
    assert paths.count()==2
    assert paths.evaluate_all('(ps)=>ps.every(p=>p.dataset.fromLane===p.dataset.toLane)')
    assert page.locator('path[data-kind="completion"]').count()==0 # Adjacent intervals are sequential.
    seed([('a','多器具','10:00','11:00',['stove','oven']),('b','交错占用','10:30','11:30',['stove','oven'])])
    assert page.locator('path[data-kind="completion"]').count()==0 # No crossovers between shared lanes.
    seed([('a','长占用','10:00','12:00',['stove','oven']),('b','同列中间步骤','10:15','11:45',['stove']),('c','同列短步骤','10:30','11:00',['stove'])])
    assert page.locator('path[data-kind="completion"][data-from-id="c"][data-to-id="a"][data-to-lane="oven"]').count()==1
    assert page.locator('path[data-kind="completion"][data-from-id="c"][data-to-id="b"]').count()==0
    # Staggered overlapping intervals join at real ends, through the next finishing tool.
    seed([('a','开始','10:00','11:00',['stove']),('b','稍后结束','10:30','11:30',['oven']),('c','中间结束','10:45','11:10',['rice'])])
    assert page.locator('path[data-kind="completion"][data-from-id="a"][data-to-id="c"]').count()==1
    assert page.locator('path[data-kind="completion"][data-from-id="c"][data-to-id="b"]').count()==1
    assert page.locator('path[data-kind="completion"][data-from-id="a"][data-to-id="b"]').count()==0
    data=plan(page);data['tasks'][2]['done']=True
    page.evaluate('([k,v])=>localStorage.setItem(k,JSON.stringify(v))',[KEY,data]);page.reload()
    page.locator('[data-filter="todo"]').click()
    assert page.locator('path[data-kind="completion"]').count()==0 # No shortcut over hidden c.
    page.locator('[data-filter="all"]').click();set_range(page,'10:00','11:05')
    assert page.locator('path[data-kind="completion"]').count()==0 # No clipped-end joins.
    set_range(page,'10:00','13:00');page.set_viewport_size({'width':375,'height':812})
    page.screenshot(path='/tmp/minchef-staggered-tools.png')
    # Example import lives in help; cancellation and failed persistence preserve both copies.
    assert page.locator('.top-actions #resetDemo').count()==0
    page.locator('[data-filter="done"]').click();page.locator('#showHelp').click()
    assert page.locator('#helpDialog #resetDemo').inner_text()=='导入示例'
    before=plan(page);memory=page.evaluate('JSON.stringify(state)')
    page.once('dialog',lambda d:d.dismiss());page.locator('#resetDemo').click()
    assert plan(page)==before and page.evaluate('JSON.stringify(state)')==memory
    page.evaluate('()=>{window.originalSet=Storage.prototype.setItem;Storage.prototype.setItem=()=>{throw new Error("Quota")}}')
    page.once('dialog',lambda d:d.accept());page.locator('#resetDemo').click()
    assert '当前排程未更改' in page.locator('#saveState').inner_text()
    assert plan(page)==before and page.evaluate('JSON.stringify(state)')==memory
    page.evaluate('()=>{Storage.prototype.setItem=window.originalSet}')
    page.once('dialog',lambda d:d.accept());page.locator('#resetDemo').click()
    assert not page.locator('#helpDialog').evaluate('(d)=>d.open')
    assert page.locator('[data-filter="all"]').evaluate('(b)=>b.classList.contains("active")')
    assert page.locator('.task-card').count()==9
    assert len(plan(page)['tasks'])==8 and '失败' not in page.locator('#saveState').inner_text()
    page.reload();assert len(plan(page)['tasks'])==8
    assert not errors,errors
    context.close()
    print('PASS: dish-name fallback, shared/staggered multi-tool edges, hidden/clipped intermediates and atomic example import from help')


def test_narrow_headers_and_person_links(browser, url, errors):
    context=browser.new_context(viewport={'width':375,'height':812},is_mobile=True,has_touch=True)
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(url);page.locator('.task-card .check').first.tap()
    data=plan(page);template=data['tasks'][0]
    data.update(timelineStart='10:00',timelineEnd='12:00',unassignedWidth=64)
    data['appliances']=[
        {'id':'oven','name':'很长很长的烤箱名称','icon':'🔆','capacity':1,'width':140},
        {'id':'chef','name':'小敏','icon':'👩🏻‍🍳','capacity':1,'width':64},
        {'id':'chef2','name':'小明','icon':'👨🏻‍🍳','capacity':1,'width':64}]
    def task(id,start,end,resources):
        return {**template,'id':id,'name':id,'start':start,'end':end,'appliances':resources,'done':False}
    def seed(tasks):
        data['tasks']=tasks
        page.evaluate('([k,v])=>localStorage.setItem(k,JSON.stringify(v))',[KEY,data]);page.reload()
    seed([task('a','10:00','10:15',['oven','chef']),task('b','10:20','10:35',['oven','chef']),
          task('c','10:40','10:55',['oven']),task('d','11:00','11:15',['oven']),task('u','11:20','11:30',[])])
    def aligned():
        for head in page.locator('.appliance-head, .unassigned-head').all():
            id=head.get_attribute('data-appliance-id')
            lane=page.locator(f'.lane[data-resource-id="{id}"]' if id else '.lane[data-unassigned]')
            h,l=head.bounding_box(),lane.bounding_box()
            assert abs(h['x']-l['x'])<.1 and abs(h['width']-l['width'])<.1,(id,h,l)
            assert abs(h['width']-head.evaluate('(e)=>parseFloat(e.style.flexBasis)'))<.1
    aligned()
    label=page.locator('[data-open-appliance="oven"] small')
    full=label.inner_text();assert '4 个步骤' in full and '上限 1' in full
    assert label.evaluate('(e)=>getComputedStyle(e).maskImage')=='none'
    resize_column(page,-76);aligned()
    assert plan(page)['appliances'][0]['width']==64
    assert label.evaluate('(e)=>e.scrollWidth>e.clientWidth')
    assert 'linear-gradient' in label.evaluate('(e)=>getComputedStyle(e).maskImage')
    assert label.inner_text()==full and label.get_attribute('title')==full
    page.screenshot(path='/tmp/minchef-narrow-headers.png')
    resize_column(page,100);aligned()
    assert label.evaluate('(e)=>e.scrollWidth<=e.clientWidth')
    assert label.evaluate('(e)=>getComputedStyle(e).maskImage')=='none'
    assert label.inner_text()==full
    # Touch resizing back to minimum must preserve geometry, then keyboard widening clears the fade.
    handle=page.locator('[data-resize-appliance="oven"]');handle.scroll_into_view_if_needed();box=handle.bounding_box()
    session=context.new_cdp_session(page)
    point={'x':box['x']+box['width']/2,'y':box['y']+box['height']/2}
    session.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[point]})
    point['x']-=100
    session.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[point]})
    session.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    aligned();assert plan(page)['appliances'][0]['width']==64
    page.reload();aligned();assert 'linear-gradient' in label.evaluate('(e)=>getComputedStyle(e).maskImage')
    page.locator('[data-resize-appliance="oven"]').focus()
    for _ in range(10):page.keyboard.press('ArrowRight')
    aligned();assert label.evaluate('(e)=>getComputedStyle(e).maskImage')=='none'
    page.locator('[data-move-appliance="oven"]').focus();page.keyboard.press('ArrowRight')
    aligned();assert plan(page)['appliances'][1]['id']=='oven'
    for width in [320,1280]:
        page.set_viewport_size({'width':width,'height':812});page.wait_for_timeout(50);aligned()
    # People participate in consecutive steps, including person-only and mixed assignments.
    seed([task('prep','10:00','10:15',['oven']),task('hands','10:20','10:45',['chef']),
          task('mixed','10:50','11:00',['oven','chef']),task('finish','11:05','11:20',['chef2'])])
    assert page.locator('path[data-from-id="prep"][data-to-id="hands"][data-to-lane="chef"]').count()==1
    assert page.locator('path[data-from-id="hands"][data-to-id="mixed"]').count()==2
    assert page.locator('path[data-from-id="mixed"][data-to-id="finish"][data-to-lane="chef2"]').count()==2
    data['tasks'][1]['done']=True
    page.evaluate('([k,v])=>localStorage.setItem(k,JSON.stringify(v))',[KEY,data]);page.reload()
    page.locator('[data-filter="todo"]').click()
    assert page.locator('path[data-from-id="hands"],path[data-to-id="hands"],path[data-from-id="prep"][data-to-id="mixed"]').count()==0
    # A person's overlapping interval joins to the tool's true finish, with clipping respected.
    seed([task('hold','10:00','11:00',['oven']),task('person','10:20','10:45',['chef'])])
    path=page.locator('path[data-kind="completion"][data-from-id="person"][data-to-id="hold"]')
    assert path.count()==1 and path.get_attribute('data-from-lane')=='chef'
    set_range(page,'10:00','10:50');assert path.count()==0
    assert not errors,errors
    context.close()
    print('PASS: narrow header/lane alignment, conditional fade/reveal, mouse/touch/keyboard resizing and mixed/person-only sequence/completion links')


def test_duration_scheduling(browser, url, errors):
    import copy
    context = browser.new_context(viewport={'width':375,'height':812},is_mobile=True,has_touch=True)
    page = context.new_page(); page.set_default_timeout(6000)
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(url); page.locator('.task-card .check').first.tap()
    base = plan(page)
    base['timelineStart'],base['timelineEnd']='10:00','12:00'
    base['appliances']=[a for a in base['appliances'] if a['id'] in ['oven','stove']]
    for a in base['appliances']: a['capacity']=1
    base['appliances'].append({'id':'chef','name':'小敏','icon':'👩🏻‍🍳','capacity':1})
    template = base['tasks'][0]
    def task(id,dish,start,end,resources,flex=False,done=False,pending=False):
        mins=lambda t:int(t[:2])*60+int(t[3:])
        result={**template,'id':id,'name':id,'dishId':base['dishes'][dish]['id'],'dish':base['dishes'][dish]['name'],'start':start,'end':end,'appliances':resources,'done':done,'timingMode':'duration' if flex else 'fixed','scheduled':not pending}
        if flex: result['duration']=mins(end)-mins(start)
        return result
    def seed(tasks,capacity=1,end='12:00'):
        data=copy.deepcopy(base); data['tasks']=tasks; data['timelineEnd']=end
        next(a for a in data['appliances'] if a['id']=='oven')['capacity']=capacity
        page.evaluate('([k,v])=>localStorage.setItem(k,JSON.stringify(v))',[KEY,data]);page.reload()
    def add_duration(duration,resources,dish=2):
        page.locator('#manageMenu').tap();page.locator(f'[data-open-dish="{base['dishes'][dish]['id']}"]').tap();page.locator('#addDishTask').tap()
        page.locator('#taskStart').fill('') # Hidden fixed-time validation must not block duration mode.
        page.locator('#taskTimingMode').select_option('duration')
        page.locator('#taskDuration').fill(str(duration));page.locator('#taskName').fill('新增步骤')
        for id in resources: page.locator(f'#applianceChecks input[value="{id}"],#peopleChecks input[value="{id}"]').check()
        page.locator('#saveTask').tap()
        assert page.locator('#scheduleDialog').evaluate('(d)=>d.open')
        added=plan(page)['tasks'][-1]
        assert added['scheduled'] is False and added['duration']==duration and added['timingMode']=='duration'
        assert page.locator(f'.task-card[data-id="{added['id']}"]').count()==0
        return added['id']
    def search():
        before=plan(page)
        page.locator('#findSchedule').tap()
        assert plan(page)==before # Searching never applies a proposal.
    def reopen(id):
        page.locator(f'[data-schedule-task="{id}"]').tap()
    seed([task('oven-fixed',0,'10:00','10:30',['oven']),task('stove-fixed',1,'10:00','10:20',['stove'])])
    id=add_duration(15,['oven','stove'])
    page.locator('#scheduleDialog [data-close-dialog]').first.tap()
    assert '待排程' in page.locator(f'[data-edit-task="{id}"]').inner_text()
    assert page.locator(f'[data-toggle-step="{id}"]').is_disabled()
    reopen(id);search()
    assert '10:30–10:45' in page.locator('#scheduleResult').inner_text()
    page.locator('#applySchedule').tap()
    assert next(t for t in plan(page)['tasks'] if t['id']==id)['start']=='10:30'
    assert next(t for t in plan(page)['tasks'] if t['id']==id)['scheduled']
    page.reload();assert next(t for t in plan(page)['tasks'] if t['id']==id)['duration']==15
    assert page.locator('.capacity-conflict').count()==0
    # Resizing a scheduled duration step keeps its persisted duration consistent.
    drag(page,page.locator(f'[data-id="{id}"] .resize-handle.bottom').first,scale(page)/12)
    resized=next(t for t in plan(page)['tasks'] if t['id']==id)
    assert resized['end']=='10:50' and resized['duration']==20
    page.reload();assert next(t for t in plan(page)['tasks'] if t['id']==id)==resized
    open_step(page,id);page.locator('#taskNote').fill('只改备注');page.locator('#saveTask').tap()
    assert not page.locator('#scheduleDialog').evaluate('(d)=>d.open')
    assert next(t for t in plan(page)['tasks'] if t['id']==id)=={**resized,'note':'只改备注'}
    # Capacity 2 allows a second dish, unlimited allows parallel use, and people also reserve capacity.
    for cap,resources,expected in [(2,['oven'],'10:00–10:15'),(0,['oven'],'10:00–10:15'),(2,['oven','chef'],'10:40–10:55')]:
        seed([task('oven-fixed',0,'10:00','11:00',['oven']),task('chef-fixed',1,'10:00','10:40',['chef'])],cap)
        add_duration(15,resources);search();assert expected in page.locator('#scheduleResult').inner_text()
        page.locator('#applySchedule').tap();assert page.locator('.capacity-conflict').count()==0
    # The new step follows this dish's existing steps, even on an unlimited tool.
    seed([task('own-prep',0,'10:00','10:30',['oven'])],0)
    add_duration(15,['oven'],dish=0);search();assert '10:30–10:45' in page.locator('#scheduleResult').inner_text()
    # Fragmented free time cannot satisfy a continuous duration, and no fixed step is moved.
    seed([task('middle-block',0,'10:10','10:20',['oven'])],end='10:30')
    id=add_duration(15,['oven']);search()
    assert '没有可用空档' in page.locator('#scheduleStatus').inner_text()
    assert page.locator('#applySchedule').is_hidden() and page.locator('#applyOptimized').is_hidden()
    pending_source=plan(page)
    pending_token=page.evaluate('encodePlan(state)')
    page.locator('#scheduleDialog [data-close-dialog]').first.tap();page.locator('#menuDialog [data-close-dialog]').tap()
    set_range(page,'10:00','11:00')
    page.locator('#manageMenu').tap();page.locator(f'[data-open-dish="{base['dishes'][2]['id']}"]').tap();reopen(id);search()
    assert '10:20–10:35' in page.locator('#scheduleResult').inner_text()
    # A pending predecessor must be arranged first.
    seed([task('pending-prep',0,'10:00','10:15',['oven'],flex=True,pending=True)])
    add_duration(15,['oven'],dish=0);search();assert '前面的待排程' in page.locator('#scheduleStatus').inner_text()
    locked=[task('completed',1,'09:00','09:15',['stove'],flex=True,done=True),task('fixed',0,'10:00','10:40',['stove'])]
    flex=[task('flex-one',1,'10:30','10:45',['oven'],flex=True),task('flex-two',1,'10:45','11:00',['oven'],flex=True)]
    seed(locked+flex)
    id=add_duration(45,['oven']);search()
    assert '11:00–11:45' in page.locator('#scheduleResult').inner_text()
    assert page.locator('#optimizationPreview').is_visible()
    assert page.locator('#optimizationChanges li').count()==2
    assert '10:30–11:15' in page.locator('#optimizedResult').inner_text()
    assert next(t for t in plan(page)['tasks'] if t['id']=='flex-one')['start']=='10:30'
    # Choosing the ordinary slot explicitly declines all suggested changes to other dishes.
    page.locator('#applySchedule').tap()
    assert plan(page)['tasks'][:4]==locked+flex
    seed(locked+flex,end='11:15')
    add_duration(45,['oven']);search()
    assert page.locator('#applySchedule').is_hidden() and page.locator('#applyOptimized').is_visible()
    assert '10:30–11:15' in page.locator('#optimizedResult').inner_text()
    seed(locked+flex)
    id=add_duration(45,['oven']);search()
    snapshot=plan(page)
    page.evaluate('() => { window.originalSet=Storage.prototype.setItem; Storage.prototype.setItem=()=>{throw new Error("Quota");}; }')
    page.locator('#applyOptimized').tap()
    assert '原排程未调整' in page.locator('#scheduleStatus').inner_text() and plan(page)==snapshot
    page.evaluate('() => { Storage.prototype.setItem=window.originalSet; }')
    page.locator('#applyOptimized').tap()
    result=plan(page)
    assert result['tasks'][:2]==locked
    assert next(t for t in result['tasks'] if t['id']=='flex-one')['start']=='10:00'
    assert next(t for t in result['tasks'] if t['id']=='flex-two')['start']=='10:15'
    assert next(t for t in result['tasks'] if t['id']==id)['start']=='10:30'
    assert page.locator('.capacity-conflict').count()==0
    page.reload();assert plan(page)==result
    # Completed steps cannot be silently turned back into pending duration work.
    open_step(page,'completed');page.locator('#taskNote').fill('已完成的备注');page.locator('#saveTask').tap()
    assert next(t for t in plan(page)['tasks'] if t['id']=='completed')=={**locked[0],'note':'已完成的备注'}
    page.locator('[data-edit-task="completed"]').tap();page.locator('#taskDuration').fill('20');page.locator('#saveTask').tap()
    assert '标为待处理' in page.locator('#taskError').inner_text()
    assert plan(page)['tasks'][0]=={**locked[0],'note':'已完成的备注'}
    seed(locked+flex)
    add_duration(45,['oven']);search()
    external=plan(page);external['tasks'][0]['note']='另一页面的新备注'
    page.evaluate('([k,v])=>localStorage.setItem(k,JSON.stringify(v))',[KEY,external])
    page.locator('#applyOptimized').tap()
    assert '排程已变化' in page.locator('#scheduleStatus').inner_text()
    assert plan(page)==external
    # New transfer metadata preserves pending mode, duration, and existing fixed anchors.
    other=browser.new_context();dest=other.new_page();dest.on('pageerror',lambda e:errors.append(str(e)))
    dest.goto(url);dest.locator('#manageMenu').click();dest.locator('#openTransfer').click()
    dest.locator('#importText').fill(pending_token);dest.locator('#previewImport').click();dest.locator('#confirmImport').click()
    assert semantic_plan(plan(dest))==semantic_plan(pending_source)
    assert len([t for t in plan(dest)['tasks'] if t.get('scheduled') is False])==1
    dest.reload();assert semantic_plan(plan(dest))==semantic_plan(pending_source)
    assert not errors,errors
    other.close();context.close()
    print('PASS: duration prompt/pending state, capacities/tools/people, continuous slots, same-dish order, optional optimization, fixed/completed locks, save failure and transfer metadata')


def test_empty_column_and_now(browser,url,errors):
    from datetime import datetime,timezone
    context=browser.new_context(viewport={'width':375,'height':812},is_mobile=True,has_touch=True,timezone_id='UTC')
    page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.clock.install(time=datetime(2026,11,6,12,0,tzinfo=timezone.utc))
    page.goto(url)
    assert page.locator('.unassigned-head,.lane[data-unassigned]').count()==0
    assert page.locator('#nowLine').is_visible()
    assert page.locator('#nowLine span').inner_text()=='now'
    assert page.locator('#nowLine span').evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)')==9
    assert page.locator('.help-button').evaluate('(e)=>{const s=getComputedStyle(e,"::before");return parseFloat(s.width)+parseFloat(s.borderLeftWidth)+parseFloat(s.borderRightWidth);}')==20
    page.locator('#manageMenu').tap();page.locator('#addDish').tap();page.locator('#addDishTask').tap();page.locator('#saveTask').tap()
    id=plan(page)['tasks'][-1]['id']
    page.locator('#menuDialog [data-close-dialog]').tap()
    assert page.locator('.unassigned-head').count()==1
    page.locator('[data-resize-unassigned]').focus();page.keyboard.press('ArrowRight')
    width=plan(page)['unassignedWidth']
    page.locator('[data-filter="done"]').tap();assert page.locator('.unassigned-head').count()==0
    page.locator('[data-filter="all"]').tap();assert abs(page.locator('.unassigned-head').bounding_box()['width']-width)<1
    open_step(page,id);page.locator('#applianceChecks input').first.check();page.locator('#saveTask').tap();page.locator('#menuDialog [data-close-dialog]').tap()
    assert page.locator('.unassigned-head').count()==0 and plan(page)['unassignedWidth']==width
    open_step(page,id);page.locator('#applianceChecks input:checked').uncheck();page.locator('#saveTask').tap();page.locator('#menuDialog [data-close-dialog]').tap()
    assert abs(page.locator('.unassigned-head').bounding_box()['width']-width)<1
    set_range(page,'16:00','19:00');assert page.locator('#nowLine').is_hidden()
    assert page.locator('.unassigned-head').count()==0
    assert not errors,errors
    context.close()
    print('PASS: empty/filtered/out-of-range unassigned column visibility, retained width, smaller help glyph and current-time label')


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
            assert abs(page.locator('.lane[data-resource-id]').first.bounding_box()['width'] - widths[0] - 60) < 1
            assert abs(page.locator('.lane[data-resource-id]').nth(1).bounding_box()['width'] - widths[1]) < 1
            resized_width = page.locator('.lane[data-resource-id]').first.bounding_box()['width']
            page.reload()
            assert abs(page.locator('.lane[data-resource-id]').first.bounding_box()['width'] - resized_width) < 1
            set_range(page, '10:15', '12:10')
            assert page.locator('.time-label').first.inner_text() == '11'
            body = page.locator('.timeline-body').bounding_box()
            for box in page.locator('.task-card').evaluate_all('(els) => els.map(e => {const r=e.getBoundingClientRect(); return {top:r.top,bottom:r.bottom};})'):
                assert box['top'] >= body['y'] - 1
                assert box['bottom'] <= body['y'] + body['height'] + 1
            assert page.locator('[data-id="t8"]').count() == 1
            set_range(page, '10:00', '22:00')
            # Simultaneous tasks remain individually visible and clickable.
            cards = page.locator('.lane[data-resource-id]').first.locator('.task-card[data-id="t6"], .task-card[data-id="t7"]')
            a, b = [cards.nth(i).bounding_box() for i in range(2)]
            assert a['x'] + a['width'] <= b['x'] or b['x'] + b['width'] <= a['x']
            # Blank names and multiple appliances, edit, completion and persistence.
            page.locator('#manageMenu').click()
            page.locator('#addDish').click()
            page.locator('#addDishTask').click()
            page.locator('#taskStart').fill('19:00')
            page.locator('#taskEnd').fill('19:30')
            page.locator('#applianceChecks input').nth(0).check()
            page.locator('#applianceChecks input').nth(1).check()
            page.locator('#saveTask').click()
            page.locator('#menuDialog [data-close-dialog]').click()
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
                page.locator('.appliance-open').first.click()
                page.locator('#deleteAppliance').click()
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
            column = mobile.locator('[data-resize-appliance]').first
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
            assert abs(mobile.locator('.lane[data-resource-id]').first.bounding_box()['width'] - after[0]) < 1
            assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert not errors, errors
            context.close()
            test_menu(browser, url, errors)
            test_appliance_capacity(browser, url, errors)
            test_people(browser, url, errors)
            test_unassigned_and_links(browser, url, errors)
            test_sequence_and_settings(browser, url, errors)
            test_transfer(browser, url, errors)
            test_mobile_compatibility(browser, url, errors)
            test_completion_links_and_compact_layout(browser, url, errors)
            test_unassigned_width_and_help(browser, url, errors)
            test_multi_tool_links_and_example(browser, url, errors)
            test_narrow_headers_and_person_links(browser, url, errors)
            test_duration_scheduling(browser, url, errors)
            test_empty_column_and_now(browser, url, errors)
            browser.close()
            print('PASS: mobile layout and real touch resizing; no JavaScript errors')
    finally:
        server.shutdown()
        server.server_close()

if __name__ == '__main__':
    run()
