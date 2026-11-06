const STORAGE_KEY = "banquet-kitchen-plan-v1";
const SAVE_MESSAGE = "排程会自动保存在当前浏览器的缓存中。";
let hourHeight = 180;
const MIN_COLUMN_WIDTH = 64;
const MAX_COLUMN_WIDTH = 800;
const SCALES = [1, 2, 2.5, 3, 4, 6];
const DRAG_STEPS = [1, 5, 10, 15, 30];

const DISH_STROKES = ["#2f6957", "#a87621", "#ad5c49", "#75649d", "#3c7c8a"];
const COLORS = ["#cfe7d4", "#f4d28a", "#eaa18f", "#c9c4e7", "#b6dce4"];
const demo = {
  resourceIconVersion: 1, visibleHours: 2.5, dragStep: 5,
  appliances: [
    { id: "stove", name: "灶台", icon: "♨️" }, { id: "oven", name: "烤箱", icon: "🔆" },
    { id: "rice", name: "电饭锅", icon: "🍚" }, { id: "steamer", name: "蒸锅", icon: "🌫️" }
  ],
  tasks: [
    { id: "t1", name: "腌制排骨", dish: "粉蒸排骨", start: "10:00", end: "10:30", appliances: ["stove"], note: "提前入味", done: true },
    { id: "t2", name: "烤制排骨", dish: "粉蒸排骨", start: "10:30", end: "12:00", appliances: ["oven"], note: "180°C", done: false },
    { id: "t3", name: "煮米饭", dish: "米饭", start: "11:00", end: "12:00", appliances: ["rice"], note: "", done: false },
    { id: "t4", name: "蒸鱼", dish: "清蒸鲈鱼", start: "11:30", end: "12:00", appliances: ["steamer"], note: "水开后 8 分钟", done: false },
    { id: "t5", name: "烧开水", dish: "白灼菜心", start: "11:30", end: "12:00", appliances: ["stove"], note: "", done: false },
    { id: "t6", name: "收汁装盘", dish: "红烧肉", start: "12:00", end: "12:30", appliances: ["stove"], note: "", done: false },
    { id: "t7", name: "焯烫菜心", dish: "白灼菜心", start: "12:00", end: "12:20", appliances: ["stove", "steamer"], note: "", done: false },
    { id: "t8", name: "保温", dish: "米饭", start: "12:00", end: "13:00", appliances: ["rice"], note: "", done: false }
  ]
};
function validTime(value) { return typeof value === "string" && /^([01]\d|2[0-3]):[0-5]\d$/.test(value); }
function validState(value) {
  if (!value || !Array.isArray(value.appliances) || !Array.isArray(value.tasks)) return false;
  if (value.visibleHours !== undefined && !SCALES.includes(value.visibleHours)) return false;
  if (value.dragStep !== undefined && !DRAG_STEPS.includes(value.dragStep)) return false;
  if (value.unassignedWidth !== undefined && (!Number.isFinite(value.unassignedWidth) || value.unassignedWidth < MIN_COLUMN_WIDTH || value.unassignedWidth > MAX_COLUMN_WIDTH)) return false;
  const ids = new Set();
  for (const a of value.appliances) {
    if (!a || typeof a.id !== "string" || ids.has(a.id) || typeof a.name !== "string" || typeof a.icon !== "string" || (a.width !== undefined && (!Number.isFinite(a.width) || a.width < MIN_COLUMN_WIDTH || a.width > MAX_COLUMN_WIDTH))) return false;
    if (a.capacity !== undefined && ![0, 1, 2, 3].includes(a.capacity)) return false;
    ids.add(a.id);
  }
  if (value.dishes !== undefined) {
    if (!Array.isArray(value.dishes)) return false;
    const dishes = new Set();
    for (const d of value.dishes) {
      if (!d || typeof d.id !== "string" || typeof d.name !== "string" || dishes.has(d.id)) return false;
      dishes.add(d.id);
    }
    if (!value.tasks.every(t => t && dishes.has(t.dishId))) return false;
  }
  const tasks = new Set();
  return value.tasks.every(t => {
    if (!t || typeof t.id !== "string" || tasks.has(t.id) || !validTime(t.start) || !validTime(t.end) || minutes(t.end) <= minutes(t.start) || !Array.isArray(t.appliances) || !t.appliances.every(id => ids.has(id)) || typeof t.name !== "string" || typeof t.dish !== "string" || typeof t.note !== "string" || typeof t.done !== "boolean") return false;
    if (t.timingMode !== undefined && !["fixed", "duration"].includes(t.timingMode)) return false;
    if (t.scheduled !== undefined && typeof t.scheduled !== "boolean") return false;
    if (t.timingMode === "duration" && (!Number.isInteger(t.duration) || t.duration < 1 || t.duration > 1439 || minutes(t.end) - minutes(t.start) !== t.duration)) return false;
    if (t.scheduled === false && (t.timingMode !== "duration" || t.done)) return false;
    tasks.add(t.id); return true;
  }) && (value.timelineStart === undefined || validTime(value.timelineStart)) && (value.timelineEnd === undefined || (validTime(value.timelineEnd) && minutes(value.timelineEnd) > minutes(value.timelineStart || "10:00")));
}
let state;
let storageWarning = "";
try {
  const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
  if (stored !== null && !validState(stored)) throw new Error("Invalid saved plan");
  state = stored || structuredClone(demo);
} catch {
  state = structuredClone(demo);
  storageWarning = "无法读取缓存，当前显示示例";
}
// The former steamer symbol now denotes a stove; migrate once to avoid ambiguity.
if (state.resourceIconVersion !== 1) {
  const replacements = { "🔥": "♨️", "♨": "♨️", "♨️": "🌫️", "▱": "🔆" };
  state.appliances.forEach(a => { a.icon = replacements[a.icon] || a.icon; });
  state.resourceIconVersion = 1;
}
state.timelineStart ||= "10:00";
if (!state.timelineEnd && state.timelineStart === "23:59") state.timelineStart = "23:58";
// Old plans did not have an explicit end: retain their visible tasks on migration.
state.timelineEnd ||= addMinutes("00:00", Math.min(1439, Math.max(minutes(state.timelineStart) + 60, 17 * 60, ...state.tasks.map(t => minutes(t.end)))));
// Keep the original storage key and migrate named step groups to stable dish IDs.
if (!state.dishes) {
  state.dishes = [];
  const byName = new Map();
  state.tasks.forEach(task => {
    if (!byName.has(task.dish)) {
      const dish = { id: `d${crypto.randomUUID()}`, name: task.dish };
      byName.set(task.dish, dish);
      state.dishes.push(dish);
    }
    task.dishId = byName.get(task.dish).id;
  });
}
state.visibleHours ||= 2.5;
state.dragStep ||= 5;
let draggedResourceId = null;
let selectedDishId = null;
let filter = "all";
let timelineDuration = 0;
let capacityConflicts = new Map();
const $ = (id) => document.getElementById(id);
function updateSaveStatus() {
  $("saveState").textContent = storageWarning || SAVE_MESSAGE;
  $("saveState").classList.toggle("save-error", Boolean(storageWarning));
  $("saveAlert").textContent = storageWarning;
  $("saveAlert").hidden = !storageWarning;
}
function save() {
  let saved = true;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    storageWarning = "";
  } catch {
    saved = false;
    storageWarning = "保存失败，请勿关闭页面";
  }
  updateSaveStatus();
  return saved;
}
function isScheduled(task) { return task.scheduled !== false; }
function minutes(time) { const [h, m] = time.split(":").map(Number); return h * 60 + m; }
function esc(value) { return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[c])); }
function display(value, fallback) { return value || fallback; }
function isPerson(resource) { return Boolean(resource && /^(👨|👩)([\u{1F3FB}-\u{1F3FF}])?\u200D🍳$/u.test(resource.icon)); }
function dishIndex(task) { return Math.max(0, state.dishes.findIndex(d => d.id === task.dishId)); }
function resourceLabel(resource) { return display(resource?.name, isPerson(resource) ? "未命名厨师" : "未命名器具"); }
function addMinutes(time, amount) {
  const value = minutes(time) + amount;
  const hours = Math.floor((value + 1440) % 1440 / 60);
  const mins = (value + 1440) % 60;
  return `${String(hours).padStart(2, "0")}:${String(mins).padStart(2, "0")}`;
}
// Only overlapping groups share space; unrelated steps use the full lane width.
function layoutTasks(tasks) {
  const sorted = [...tasks].sort((a, b) => minutes(a.start) - minutes(b.start) || minutes(a.end) - minutes(b.end));
  const positions = new Map();
  let group = [], groupEnd = -1;
  function placeGroup() {
    const columns = [];
    for (const task of group) {
      let column = columns.findIndex(end => end <= minutes(task.start));
      if (column < 0) column = columns.length;
      columns[column] = minutes(task.end);
      positions.set(task.id, { column });
    }
    group.forEach(task => positions.get(task.id).count = columns.length);
  }
  for (const task of sorted) {
    if (minutes(task.start) >= groupEnd) { placeGroup(); group = []; }
    group.push(task);
    groupEnd = Math.max(groupEnd, minutes(task.end));
  }
  placeGroup();
  return positions;
}
// Capacity counts distinct dishes in each real interval, not the number of steps.
// End points are exclusive so back-to-back dishes do not collide.
function findCapacityConflicts() {
  const conflicts = new Map();
  for (const appliance of state.appliances) {
    if (!appliance.capacity) continue;
    const tasks = state.tasks.filter(t => isScheduled(t) && t.appliances.includes(appliance.id));
    const boundaries = [...new Set(tasks.flatMap(t => [minutes(t.start), minutes(t.end)]))].sort((a, b) => a - b);
    for (const time of boundaries) {
      const active = tasks.filter(t => minutes(t.start) <= time && minutes(t.end) > time);
      if (new Set(active.map(t => t.dishId)).size <= appliance.capacity) continue;
      active.forEach(t => {
        if (!conflicts.has(t.id)) conflicts.set(t.id, new Set());
        conflicts.get(t.id).add(resourceLabel(appliance));
      });
    }
  }
  return conflicts;
}
function sizeTimeline() {
  const wrap = document.querySelector(".planner-wrap");
  const footer = document.querySelector(".timeline-footer");
  const bottomSpace = footer.getBoundingClientRect().height + parseFloat(getComputedStyle(document.querySelector(".app-shell")).paddingBottom);
  const height = Math.max(180, window.innerHeight - (wrap.getBoundingClientRect().top + window.scrollY) - bottomSpace - 2);
  wrap.style.height = `${height}px`;
  hourHeight = (height - 64) / (state.visibleHours || 2.5);
  $("planner").style.setProperty("--hour", `${hourHeight}px`);
}
function render() {
  const start = minutes(state.timelineStart);
  capacityConflicts = findCapacityConflicts();
  $("capacityStatus").textContent = capacityConflicts.size ? `${capacityConflicts.size} 个步骤超出器具或人力容量` : "";
  updateSaveStatus();
  const peopleCount = state.appliances.filter(isPerson).length;
  $("summary").innerHTML = `<div class="stat"><strong>${state.dishes.length}</strong><span>道菜品</span></div><div class="stat"><strong>${state.appliances.length - peopleCount}</strong><span>件器具</span></div>${peopleCount ? `<div class="stat"><strong>${peopleCount}</strong><span>位厨师</span></div>` : ""}<div class="stat"><strong>${state.tasks.filter(t => t.done).length}/${state.tasks.length}</strong><span>步骤完成</span></div>`;
  sizeTimeline();
  const end = minutes(state.timelineEnd);
  timelineDuration = end - start;
  $("planner").style.setProperty("--timeline-height", `${timelineDuration / 60 * hourHeight}px`);
  const visible = state.tasks.filter(t => isScheduled(t) && (filter === "all" || (filter === "done" ? t.done : !t.done)) && minutes(t.end) > start && minutes(t.start) < end);
  const unassigned = visible.filter(t => t.appliances.length === 0);
  const showUnassigned = unassigned.length > 0;
  const unassignedLayout = layoutTasks(unassigned);
  const layouts = state.appliances.map(a => layoutTasks(visible.filter(t => t.appliances.includes(a.id))));
  const defaultWidth = Math.max(MIN_COLUMN_WIDTH, (document.querySelector(".planner-wrap").clientWidth - 28) / 4);
  const widths = state.appliances.map(a => a.width || defaultWidth);
  const unassignedWidth = showUnassigned ? state.unassignedWidth || defaultWidth : 0;
  $("planner").style.width = `calc(var(--sidebar) + ${widths.reduce((a, b) => a + b, 0) + unassignedWidth + 48}px)`;
  $("applianceHeads").innerHTML = (showUnassigned ? `<div class="unassigned-head" style="flex-basis:${unassignedWidth}px"><strong>无器具</strong><small>${state.tasks.filter(t => isScheduled(t) && t.appliances.length === 0).length} 个步骤</small><span class="column-resize" data-resize-unassigned role="separator" tabindex="0" aria-label="调整无器具列宽" aria-orientation="vertical" aria-valuemin="${MIN_COLUMN_WIDTH}" aria-valuemax="${MAX_COLUMN_WIDTH}" aria-valuenow="${Math.round(unassignedWidth)}"></span></div>` : "") + state.appliances.map((a, i) => `<div class="appliance-head ${draggedResourceId === a.id ? "reordering" : ""}" data-appliance-id="${esc(a.id)}" style="flex-basis:${widths[i]}px"><button type="button" class="appliance-open ${a.name.trim() ? "" : "icon-only"}" data-open-appliance="${esc(a.id)}" aria-label="设置${esc(resourceLabel(a))}"><span class="tool-icon">${esc(a.icon)}</span>${a.name.trim() ? `<strong>${esc(a.name)}</strong><small>${state.tasks.filter(t => isScheduled(t) && t.appliances.includes(a.id)).length} 个步骤${a.capacity ? ` · 上限 ${a.capacity}` : ""}</small>` : ""}</button><button type="button" class="column-move" data-move-appliance="${esc(a.id)}" aria-label="左右拖动排序${esc(resourceLabel(a))}" title="左右拖动排序">⠿</button><span class="column-resize" data-resize-appliance="${esc(a.id)}" role="separator" tabindex="0" aria-label="调整${esc(resourceLabel(a))}列宽" aria-orientation="vertical" aria-valuemin="${MIN_COLUMN_WIDTH}" aria-valuemax="${MAX_COLUMN_WIDTH}" aria-valuenow="${Math.round(widths[i])}"></span></div>`).join("") + '<div class="add-appliance-cell"><button id="addAppliance" type="button" aria-label="添加器具或人员" title="添加器具或人员">＋</button></div>';
  $("addAppliance").onclick = () => openAppliance();
  const firstHour = Math.ceil(start / 60) * 60;
  $("timeAxis").innerHTML = Array.from({ length: Math.max(0, Math.ceil((end - firstHour) / 60)) }, (_, index) => {
    const time = firstHour + index * 60;
    return `<div class="time-label" style="top:${(time - start) / 60 * hourHeight}px">${Math.floor(time / 60)}</div>`;
  }).join("");
  $("lanes").style.backgroundPositionY = `${(firstHour - start) / 60 * hourHeight}px`;
  $("lanes").innerHTML = (showUnassigned ? `<div class="lane" data-unassigned style="flex-basis:${unassignedWidth}px">${unassigned.map(t => taskCard(t, unassignedLayout)).join("")}</div>` : "") + state.appliances.map((a, i) => `<div class="lane" data-resource-id="${esc(a.id)}" data-person="${isPerson(a)}" style="flex-basis:${widths[i]}px">${visible.filter(t => t.appliances.includes(a.id)).map(t => taskCard(t, layouts[i])).join("")}</div>`).join("");
  renderConnections();
  renderMenu();
  document.querySelectorAll("[data-open-appliance]").forEach(b => b.onclick = () => openAppliance(b.dataset.openAppliance));
  document.querySelectorAll(".task-card").forEach(card => {
    card.onclick = (event) => { if (!event.target.closest(".resize-handle, .move-handle")) openTask(card.dataset.id); };
    card.querySelector(".check").onclick = (event) => {
      event.stopPropagation();
      const task = state.tasks.find(t => t.id === card.dataset.id);
      if (task) { task.done = !task.done; save(); render(); }
    };
    card.querySelectorAll(".resize-handle, .move-handle").forEach(handle => handle.addEventListener("pointerdown", startResize));
  });
  document.querySelectorAll("[data-resize-appliance], [data-resize-unassigned]").forEach(handle => {
    handle.addEventListener("pointerdown", startColumnResize);
    handle.addEventListener("keydown", e => {
      if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
      e.preventDefault();
      const unassigned = handle.hasAttribute("data-resize-unassigned");
      const target = unassigned ? state : state.appliances.find(a => a.id === handle.dataset.resizeAppliance);
      const key = unassigned ? "unassignedWidth" : "width";
      const id = handle.dataset.resizeAppliance;
      target[key] = Math.max(MIN_COLUMN_WIDTH, Math.min(MAX_COLUMN_WIDTH, handle.parentElement.getBoundingClientRect().width + (e.key === "ArrowRight" ? 10 : -10)));
      save(); render();
      document.querySelectorAll("[data-resize-appliance], [data-resize-unassigned]").forEach(next => {
        if (unassigned ? next.hasAttribute("data-resize-unassigned") : next.dataset.resizeAppliance === id) next.focus();
      });
    });
  });
  document.querySelectorAll("[data-move-appliance], .appliance-open").forEach(handle => {
    handle.addEventListener("pointerdown", startColumnMove);
    handle.addEventListener("keydown", e => {
      if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
      e.preventDefault();
      const id = handle.dataset.moveAppliance || handle.dataset.openAppliance;
      const i = state.appliances.findIndex(a => a.id === id);
      const to = Math.max(0, Math.min(state.appliances.length - 1, i + (e.key === "ArrowRight" ? 1 : -1)));
      const [resource] = state.appliances.splice(i, 1);
      state.appliances.splice(to, 0, resource);
      save(); render();
      document.querySelectorAll("[data-move-appliance]").forEach(next => { if (next.dataset.moveAppliance === resource.id) next.focus(); });
    });
  });
  updateNowLine();
}
function taskCard(task, layout) {
  const top = Math.max(0, (minutes(task.start) - minutes(state.timelineStart)) / 60 * hourHeight);
  const height = (Math.min(minutes(task.end), minutes(state.timelineEnd)) - Math.max(minutes(task.start), minutes(state.timelineStart))) / 60 * hourHeight;
  const { column, count } = layout.get(task.id);
  const index = dishIndex(task);
  const warning = capacityConflicts.has(task.id) ? ` · 占用超限：${[...capacityConflicts.get(task.id)].join("、")}` : "";
  const name = display(task.name.trim(), display(task.dish.trim(), "未命名菜品"));
  const title = `${name} · ${display(task.dish, "未命名菜品")} ${task.start}–${task.end}${warning}`;
  return `<article class="task-card ${warning ? "capacity-conflict" : ""} ${height < 48 ? "short" : ""} ${task.done ? "done" : ""}" data-id="${esc(task.id)}" title="${esc(title)}" style="top:${top}px;height:${height}px;left:calc(${column / count * 100}% + ${count > 1 ? 1 : 4}px);width:calc(${100 / count}% - ${count > 1 ? 2 : 8}px);background:${COLORS[index % COLORS.length]}"><span class="resize-handle top" data-edge="start" title="拖动调整开始时间"></span><button type="button" class="move-handle" data-edge="move" aria-label="拖动移动步骤">⠿</button><button type="button" class="check" aria-label="${task.done ? "标为待处理" : "标为完成"}">${task.done ? "✓" : ""}</button><strong>${esc(name)}</strong><small>${task.start}–${task.end} · ${esc(display(task.dish, "未命名菜品"))}${task.note ? ` · ${esc(task.note)}` : ""}${warning ? " · 占用超限" : ""}</small><span class="resize-handle bottom" data-edge="end" title="拖动调整结束时间"></span></article>`;
}
// A predecessor must finish before this step starts. Tied latest finishes allow merges.
// Include hidden tasks when choosing predecessors so filtering never invents shortcuts.
function renderConnections() {
  const lanes = $("lanes");
  const bounds = lanes.getBoundingClientRect();
  const nodes = new Map();
  lanes.querySelectorAll(".lane:not([data-person='true']) .task-card").forEach(card => {
    const rect = card.getBoundingClientRect();
    const id = card.dataset.id;
    if (!nodes.has(id)) nodes.set(id, []);
    nodes.get(id).push({ x: rect.left - bounds.left + rect.width / 2, top: rect.top - bounds.top, bottom: rect.bottom - bounds.top, lane: card.parentElement.dataset.resourceId || "unassigned" });
  });
  const people = new Set(state.appliances.filter(isPerson).map(a => a.id));
  const paths = [];
  const addConnection = (from, to, kind, fromLane = null) => {
    const completion = kind === "completion";
    // A clipped bottom is not the actual finish of the step.
    if (completion && (minutes(from.end) > minutes(state.timelineEnd) || minutes(to.end) > minutes(state.timelineEnd))) return;
    for (const source of nodes.get(from.id) || []) for (const target of nodes.get(to.id) || []) {
      if (fromLane !== null && source.lane !== fromLane) continue;
      if (completion && source.lane === target.lane) continue;
      // Shared lanes continue vertically; avoid crossing their duplicate cards.
      if (source.lane !== target.lane && toolLanes(from).includes(target.lane) && toolLanes(to).includes(source.lane)) continue;
      const y1 = source.bottom, y2 = completion ? target.bottom : target.top;
      const bend = Math.max(24, Math.abs(y2 - y1) * .45);
      const arc = Math.abs(source.x - target.x) < 1 ? 16 : 0;
      const targetControl = completion ? y2 + bend : y2 - bend;
      const d = `M ${source.x} ${y1} C ${source.x + arc} ${y1 + bend}, ${target.x + arc} ${targetControl}, ${target.x} ${y2}`;
      paths.push(`<path data-kind="${kind}" data-from-id="${esc(from.id)}" data-to-id="${esc(to.id)}" data-from-lane="${esc(source.lane)}" data-to-lane="${esc(target.lane)}" d="${d}" stroke="${DISH_STROKES[dishIndex(from) % DISH_STROKES.length]}"/>`);
    }
  };
  const toolLanes = task => task.appliances.length ? task.appliances.filter(id => !people.has(id)) : ["unassigned"];
  const continues = (from, to) => from.id !== to.id && minutes(to.start) < minutes(from.end)
    && (minutes(to.end) > minutes(from.end) || to.end === from.end && minutes(to.start) < minutes(from.start));
  for (const dish of state.dishes) {
    const tasks = state.tasks.filter(t => isScheduled(t) && t.dishId === dish.id && (t.appliances.length === 0 || t.appliances.some(id => !people.has(id)))).sort((a, b) => minutes(a.start) - minutes(b.start));
    for (const to of tasks) {
      const candidates = tasks.filter(from => from.id !== to.id && minutes(from.end) <= minutes(to.start));
      const latestEnd = Math.max(-1, ...candidates.map(from => minutes(from.end)));
      for (const from of candidates.filter(from => minutes(from.end) === latestEnd)) addConnection(from, to, "sequence");
      // Each tool finishes into the next still-active tool interval. Choose on
      // the full plan so hidden intermediates cannot create false shortcuts.
      for (const lane of toolLanes(to)) {
        const candidates = tasks.filter(outer => continues(to, outer) && toolLanes(outer).some(id => id !== lane));
        const nextEnd = Math.min(Infinity, ...candidates.map(outer => minutes(outer.end)));
        const next = candidates.filter(outer => minutes(outer.end) === nextEnd);
        const latestStart = Math.max(-1, ...next.map(outer => minutes(outer.start)));
        for (const outer of next.filter(outer => minutes(outer.start) === latestStart)) addConnection(to, outer, "completion", lane);
      }
    }
  }
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.classList.add("dish-connections");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("viewBox", `0 0 ${Math.max(1, bounds.width)} ${Math.max(1, bounds.height)}`);
  svg.innerHTML = paths.join("");
  lanes.prepend(svg);
}
function updateNowLine() {
  const now = new Date();
  const current = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
  const offset = current - minutes(state.timelineStart);
  const line = $("nowLine");
  line.style.top = `${Math.max(0, Math.min(timelineDuration / 60 * hourHeight, offset / 60 * hourHeight))}px`;
  line.hidden = offset < 0 || offset > timelineDuration;
}
function startResize(event) {
  if (!event.isPrimary || event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  const task = state.tasks.find(t => t.id === event.currentTarget.closest(".task-card").dataset.id);
  if (!task) return;
  const edge = event.currentTarget.dataset.edge;
  const initialY = event.clientY;
  const dragScale = hourHeight;
  const initialStart = minutes(task.start), initialEnd = minutes(task.end);
  const step = state.dragStep || 5;
  const minimumDuration = Math.min(step, initialEnd - initialStart);
  const boundDelta = (delta, min, max) => Math.max(Math.ceil(min / step) * step, Math.min(Math.floor(max / step) * step, delta));
  const pointerId = event.pointerId;
  const planner = $("planner");
  planner.setPointerCapture(pointerId);
  const move = (e) => {
    if (e.pointerId !== pointerId) return;
    const delta = Math.round((e.clientY - initialY) / dragScale * 60 / step) * step;
    if (edge === "move") {
      const shift = boundDelta(delta, -initialStart, 1439 - initialEnd);
      task.start = addMinutes("00:00", initialStart + shift);
      task.end = addMinutes("00:00", initialEnd + shift);
    } else if (edge === "start") {
      task.start = addMinutes("00:00", initialStart + boundDelta(delta, -initialStart, initialEnd - minimumDuration - initialStart));
    } else {
      task.end = addMinutes("00:00", initialEnd + boundDelta(delta, initialStart + minimumDuration - initialEnd, 1439 - initialEnd));
    }
    if (task.timingMode === "duration") task.duration = minutes(task.end) - minutes(task.start);
    render();
  };
  const finish = (e) => {
    if (e.pointerId !== pointerId) return;
    document.removeEventListener("pointermove", move);
    document.removeEventListener("pointerup", finish);
    document.removeEventListener("pointercancel", finish);
    if (planner.hasPointerCapture(pointerId)) planner.releasePointerCapture(pointerId);
    if (e.type === "pointercancel") {
      task.start = addMinutes("00:00", initialStart);
      task.end = addMinutes("00:00", initialEnd);
      if (task.timingMode === "duration") task.duration = initialEnd - initialStart;
    }
    save(); render();
  };
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", finish);
  document.addEventListener("pointercancel", finish);
}
function startColumnResize(event) {
  if (!event.isPrimary || event.button !== 0) return;
  event.preventDefault();
  const unassigned = event.currentTarget.hasAttribute("data-resize-unassigned");
  const target = unassigned ? state : state.appliances.find(a => a.id === event.currentTarget.dataset.resizeAppliance);
  const key = unassigned ? "unassignedWidth" : "width";
  const originalWidth = target[key];
  const initialWidth = event.currentTarget.parentElement.getBoundingClientRect().width;
  const initialX = event.clientX, pointerId = event.pointerId;
  const planner = $("planner");
  planner.setPointerCapture(pointerId);
  const move = e => {
    if (e.pointerId !== pointerId) return;
    target[key] = Math.max(MIN_COLUMN_WIDTH, Math.min(MAX_COLUMN_WIDTH, initialWidth + e.clientX - initialX));
    render();
  };
  const finish = e => {
    if (e.pointerId !== pointerId) return;
    document.removeEventListener("pointermove", move);
    document.removeEventListener("pointerup", finish);
    document.removeEventListener("pointercancel", finish);
    if (planner.hasPointerCapture(pointerId)) planner.releasePointerCapture(pointerId);
    if (e.type === "pointercancel") {
      if (originalWidth === undefined) delete target[key];
      else target[key] = originalWidth;
    }
    save(); render();
  };
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", finish);
  document.addEventListener("pointercancel", finish);
}
function startColumnMove(event) {
  if (!event.isPrimary || event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  const id = event.currentTarget.dataset.moveAppliance || event.currentTarget.dataset.openAppliance;
  const original = [...state.appliances];
  const pointerId = event.pointerId, initialX = event.clientX;
  let clientX = initialX, moving = false, frame;
  const planner = $("planner"), wrap = document.querySelector(".planner-wrap");
  const update = () => {
    if (!moving) return;
    const otherHeads = [...document.querySelectorAll("[data-appliance-id]")].filter(el => el.dataset.applianceId !== id);
    const to = otherHeads.filter(el => { const r = el.getBoundingClientRect(); return clientX > r.left + r.width / 2; }).length;
    const from = state.appliances.findIndex(a => a.id === id);
    if (from !== to) {
      const [resource] = state.appliances.splice(from, 1);
      state.appliances.splice(to, 0, resource);
      render();
    }
  };
  const scroll = () => {
    if (moving) {
      const r = wrap.getBoundingClientRect();
      if (clientX < r.left + 28) wrap.scrollLeft -= 12;
      else if (clientX > r.right - 28) wrap.scrollLeft += 12;
      update();
    }
    frame = requestAnimationFrame(scroll);
  };
  const move = e => {
    if (e.pointerId !== pointerId) return;
    clientX = e.clientX;
    if (!moving && Math.abs(clientX - initialX) > 6) {
      moving = true; draggedResourceId = id;
      planner.setPointerCapture(pointerId);
      render();
    }
    update();
  };
  const finish = e => {
    if (e.pointerId !== pointerId) return;
    cancelAnimationFrame(frame);
    document.removeEventListener("pointermove", move);
    document.removeEventListener("pointerup", finish);
    document.removeEventListener("pointercancel", finish);
    document.removeEventListener("keydown", escape);
    if (planner.hasPointerCapture(pointerId)) planner.releasePointerCapture(pointerId);
    if (e.type === "pointercancel") state.appliances = original;
    draggedResourceId = null;
    if (moving) { save(); render(); }
  };
  const escape = e => { if (e.key === "Escape") { e.preventDefault(); finish({ pointerId, type: "pointercancel" }); } };
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", finish);
  document.addEventListener("pointercancel", finish);
  document.addEventListener("keydown", escape);
  frame = requestAnimationFrame(scroll);
}
function renderMenu() {
  const dish = state.dishes.find(d => d.id === selectedDishId);
  if (!dish) selectedDishId = null;
  $("menuTitle").textContent = dish ? display(dish.name, "未命名菜品") : "菜单";
  for (const id of ["menuBack", "dishForm", "deleteDish", "addDishTask"]) $(id).hidden = !dish;
  $("addDish").hidden = Boolean(dish);
  $("openTransfer").hidden = Boolean(dish);
  if (dish) {
    // Keep a name draft through viewport/keyboard changes, even after blur.
    if ($("dishName").dataset.editing !== dish.id) {
      $("dishName").value = dish.name;
      $("dishName").dataset.editing = dish.id;
    }
    const tasks = state.tasks.filter(t => t.dishId === dish.id).sort((a, b) => Number(!isScheduled(a)) - Number(!isScheduled(b)) || minutes(a.start) - minutes(b.start));
    $("menuList").innerHTML = tasks.map(t => {
      const tools = t.appliances.map(id => { const a = state.appliances.find(a => a.id === id); return `${a?.icon || ""} ${resourceLabel(a)}`; }).join("、") || "未分配器具或人力";
      return `<div class="step-row"><button type="button" class="step-check ${t.done ? "done" : ""}" data-toggle-step="${esc(t.id)}" aria-label="${t.done ? "标为待处理" : "标为完成"}" aria-pressed="${t.done}" ${isScheduled(t) ? "" : "disabled"}>${t.done ? "✓" : "○"}</button><button type="button" class="step-edit" data-edit-task="${esc(t.id)}"><strong>${esc(display(t.name, "未命名步骤"))}</strong><span>${isScheduled(t) ? `${t.start}–${t.end}` : `${t.duration} 分钟 · 待排程`} · ${esc(tools)}${capacityConflicts.has(t.id) ? " · 占用超限" : ""}</span></button>${t.timingMode === "duration" && !t.done ? `<button type="button" class="button button-quiet" data-schedule-task="${esc(t.id)}">排程</button>` : ""}</div>`;
    }).join("") || '<p class="empty-state">还没有步骤，点下方添加。</p>';
    document.querySelectorAll("[data-schedule-task]").forEach(b => b.onclick = () => openScheduling(b.dataset.scheduleTask));
    document.querySelectorAll("[data-edit-task]").forEach(b => b.onclick = () => openTask(b.dataset.editTask));
    document.querySelectorAll("[data-toggle-step]").forEach(b => b.onclick = () => {
      const task = state.tasks.find(t => t.id === b.dataset.toggleStep);
      if (!isScheduled(task)) return;
      task.done = !task.done; save(); render();
      document.querySelectorAll("[data-toggle-step]").forEach(next => { if (next.dataset.toggleStep === task.id) next.focus(); });
    });
  } else {
    delete $("dishName").dataset.editing;
    $("menuList").innerHTML = state.dishes.map(d => {
      const tasks = state.tasks.filter(t => t.dishId === d.id);
      return `<button type="button" class="menu-item" data-open-dish="${esc(d.id)}"><strong>${esc(display(d.name, "未命名菜品"))}</strong><span>${tasks.filter(t => t.done).length}/${tasks.length} 步骤完成 ›</span></button>`;
    }).join("") || '<p class="empty-state">还没有菜品，点下方添加。</p>';
    document.querySelectorAll("[data-open-dish]").forEach(b => b.onclick = () => { selectedDishId = b.dataset.openDish; renderMenu(); });
  }
}
function openMenu() {
  selectedDishId = null;
  renderMenu();
  $("menuDialog").showModal();
}
function openTask(id = "", dishId = "") {
  const task = state.tasks.find(t => t.id === id);
  const previous = state.tasks.filter(t => isScheduled(t) && t.dishId === dishId).sort((a, b) => minutes(b.end) - minutes(a.end))[0];
  const start = Math.min(1438, previous ? minutes(previous.end) : minutes(state.timelineStart));
  $("taskDialogTitle").textContent = task ? "编辑步骤" : "添加步骤";
  $("taskId").value = id;
  $("taskName").value = task?.name || "";
  $("taskDish").innerHTML = state.dishes.map(d => `<option value="${esc(d.id)}">${esc(display(d.name, "未命名菜品"))}</option>`).join("") + '<option value="__new__">＋ 新菜品</option>';
  $("taskDish").value = task?.dishId || dishId || "__new__";
  $("newDishLabel").hidden = $("taskDish").value !== "__new__";
  $("taskNewDish").value = "";
  $("taskStart").value = task?.start || addMinutes("00:00", start);
  $("taskEnd").value = task?.end || addMinutes("00:00", Math.min(1439, start + 30));
  $("taskNote").value = task?.note || "";
  $("taskError").textContent = "";
  $("taskTimingMode").value = task?.timingMode || "fixed";
  $("taskDuration").value = task?.duration || 30;
  updateTimingFields();
  const choice = a => `<label class="check-item"><input type="checkbox" value="${esc(a.id)}" ${task?.appliances.includes(a.id) ? "checked" : ""}>${esc(a.icon)} ${esc(resourceLabel(a))}</label>`;
  $("applianceChecks").innerHTML = state.appliances.filter(a => !isPerson(a)).map(choice).join("") || '<span class="empty-state">可稍后在时间轴右侧添加器具。</span>';
  $("peopleChecks").innerHTML = state.appliances.filter(isPerson).map(choice).join("") || '<span class="empty-state">在时间轴右侧添加 👨🏻‍🍳 或 👩🏻‍🍳，即可在此选择参与者。</span>';
  $("deleteTask").hidden = !task;
  $("taskDialog").showModal();
}
function updateTimingFields() {
  const duration = $("taskTimingMode").value === "duration";
  $("fixedTimeFields").hidden = duration;
  $("durationFields").hidden = !duration;
  $("taskStart").disabled = duration; $("taskEnd").disabled = duration;
  $("taskDuration").disabled = !duration; $("taskDuration").required = duration;
}
function closeDialog(id) {
  const dialog = $(id);
  if (dialog?.open) dialog.close();
}
function updateResourceLabels() {
  const person = isPerson({ icon: $("applianceIcon").value });
  $("applianceNameLabel").textContent = person ? "人员名称" : "器具名称";
  $("applianceCapacityLabel").textContent = person ? "最多同时参与的菜品数" : "最多同时占用的菜品数";
  $("applianceDialogTitle").textContent = $("applianceId").value ? (person ? "人员设置" : "器具设置") : (person ? "添加人员" : "添加器具");
  $("deleteAppliance").textContent = person ? "删除人员" : "删除器具";
  $("saveAppliance").textContent = $("applianceId").value ? "保存设置" : (person ? "添加人员" : "添加器具");
}
function openAppliance(id = "") {
  const appliance = state.appliances.find(a => a.id === id);
  $("applianceId").value = id;
  $("applianceDialogTitle").textContent = appliance ? "器具设置" : "添加器具";
  $("applianceName").value = appliance?.name || "";
  $("applianceIcon").querySelectorAll("[data-legacy]").forEach(option => option.remove());
  if (appliance && ![...$("applianceIcon").options].some(option => option.value === appliance.icon)) {
    const option = new Option(`${appliance.icon} 原图标`, appliance.icon);
    option.dataset.legacy = "true";
    $("applianceIcon").add(option);
  }
  $("applianceIcon").value = appliance?.icon || "🧰";
  updateResourceLabels();
  $("applianceCapacity").value = String(appliance?.capacity || 0);
  $("deleteAppliance").hidden = !appliance;
  updateOrderButtons();
  $("applianceDialog").showModal();
}
function updateOrderButtons() {
  const i = state.appliances.findIndex(a => a.id === $("applianceId").value);
  $("resourceOrder").hidden = i < 0;
  $("moveResourceLeft").disabled = i <= 0;
  $("moveResourceRight").disabled = i < 0 || i === state.appliances.length - 1;
}
function moveResourceBy(offset) {
  const i = state.appliances.findIndex(a => a.id === $("applianceId").value);
  const to = i + offset;
  if (i < 0 || to < 0 || to >= state.appliances.length) return;
  const [resource] = state.appliances.splice(i, 1); state.appliances.splice(to, 0, resource);
  save(); render(); updateOrderButtons();
}
$("moveResourceLeft").onclick = () => moveResourceBy(-1);
$("moveResourceRight").onclick = () => moveResourceBy(1);
function deleteAppliance(id) {
  if (!confirm("删除后会解除步骤关联，步骤仍会保留。确定删除吗？")) return;
  state.appliances = state.appliances.filter(a => a.id !== id); state.tasks.forEach(t => t.appliances = t.appliances.filter(a => a !== id)); closeDialog("applianceDialog"); save(); render();
}
document.querySelectorAll(".filter").forEach(b => b.onclick = () => { filter = b.dataset.filter; document.querySelectorAll(".filter").forEach(x => x.classList.toggle("active", x === b)); render(); });
$("taskTimingMode").onchange = updateTimingFields;
$("showHelp").onclick = () => $("helpDialog").showModal();
$("applianceIcon").onchange = updateResourceLabels;
$("deleteAppliance").onclick = () => deleteAppliance($("applianceId").value);
$("manageMenu").onclick = openMenu;
$("taskDish").onchange = () => { $("newDishLabel").hidden = $("taskDish").value !== "__new__"; };
$("menuBack").onclick = () => { selectedDishId = null; renderMenu(); };
$("addDish").onclick = () => {
  const dish = { id: `d${crypto.randomUUID()}`, name: "" };
  state.dishes.push(dish); selectedDishId = dish.id; save(); render(); $("dishName").focus();
};
$("addDishTask").onclick = () => openTask("", selectedDishId);
$("dishForm").onsubmit = e => {
  e.preventDefault();
  const dish = state.dishes.find(d => d.id === selectedDishId);
  dish.name = $("dishName").value.trim();
  $("dishName").value = dish.name;
  state.tasks.filter(t => t.dishId === dish.id).forEach(t => t.dish = dish.name);
  save(); render();
};
$("deleteDish").onclick = () => {
  if (!confirm("删除这道菜及其所有步骤？")) return;
  state.tasks = state.tasks.filter(t => t.dishId !== selectedDishId);
  state.dishes = state.dishes.filter(d => d.id !== selectedDishId);
  selectedDishId = null; save(); render();
};
$("setTimelineStart").onclick = () => { $("timelineStart").value = state.timelineStart; $("timelineEnd").value = state.timelineEnd; $("timelineScale").value = String(state.visibleHours || 2.5); $("timelineStep").value = String(state.dragStep || 5); $("timelineError").textContent = ""; $("timelineDialog").showModal(); };
document.querySelectorAll("[data-close-dialog]").forEach(button => button.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); closeDialog(button.dataset.closeDialog); }));
document.querySelectorAll("dialog").forEach(dialog => dialog.addEventListener("click", (e) => { if (e.target !== dialog) return;
  const box = dialog.getBoundingClientRect();
  if (e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom) dialog.close(); }));
$("taskForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const id = $("taskId").value || `t${crypto.randomUUID()}`;
  const name = $("taskName").value.trim();

  const mode = $("taskTimingMode").value;
  const existing = state.tasks.find(t => t.id === id);
  let start = $("taskStart").value, end = $("taskEnd").value;
  const duration = Number($("taskDuration").value);
  const appliances = [...document.querySelectorAll("#applianceChecks input:checked, #peopleChecks input:checked")].map(x => x.value);
  const keepSchedule = mode === "duration" && existing?.timingMode === "duration" && isScheduled(existing) && duration === existing.duration
    && $("taskDish").value === existing.dishId && appliances.length === existing.appliances.length && appliances.every(id => existing.appliances.includes(id));
  if (mode === "duration") {
    if (!Number.isInteger(duration) || duration < 1 || duration > 1439) { $("taskError").textContent = "请填写 1–1439 分钟。"; return; }
    if (existing?.done && !keepSchedule) { $("taskError").textContent = "请先将此步骤标为待处理，再使用所需时间排程。"; return; }
    const provisionalStart = Math.max(0, Math.min(1439 - duration, validTime(start) ? minutes(start) : minutes(state.timelineStart)));
    start = addMinutes("00:00", provisionalStart); end = addMinutes("00:00", provisionalStart + duration);
  }
  if (!validTime(start) || !validTime(end) || minutes(end) <= minutes(start)) {
    $("taskError").textContent = "结束时间必须晚于开始时间"; return;
  }
  let dish = state.dishes.find(d => d.id === $("taskDish").value);
  if (!dish) {
    const name = $("taskNewDish").value.trim();
    dish = { id: `d${crypto.randomUUID()}`, name }; state.dishes.push(dish);
  }
  const data = { id, name, dish: dish.name, dishId: dish.id, start, end, appliances, note: $("taskNote").value.trim(), done: existing?.done || false, timingMode: mode, ...(mode === "duration" ? { duration, scheduled: keepSchedule } : { scheduled: true }) };
  if ($("menuDialog").open) selectedDishId = dish.id;
  const index = state.tasks.findIndex(t => t.id === id);
  index >= 0 ? state.tasks.splice(index, 1, data) : state.tasks.push(data);
  closeDialog("taskDialog"); save(); render();
  if (mode === "duration" && !keepSchedule) openScheduling(id);
});
$("applianceForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const name = $("applianceName").value.trim();
  const appliance = state.appliances.find(a => a.id === $("applianceId").value);
  const settings = { name, icon: $("applianceIcon").value, capacity: Number($("applianceCapacity").value) };
  if (appliance) Object.assign(appliance, settings);
  else state.appliances.push({ id: `a${crypto.randomUUID()}`, ...settings });
  $("applianceForm").reset(); closeDialog("applianceDialog"); save(); render();
  if (!appliance) document.querySelector(".planner-wrap").scrollLeft = $("planner").offsetWidth;
});
$("timelineForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const start = $("timelineStart").value, end = $("timelineEnd").value;
  if (!validTime(start) || !validTime(end) || minutes(end) <= minutes(start)) {
    $("timelineError").textContent = "结束时间必须晚于起始时间";
    return;
  }
  const visibleHours = Number($("timelineScale").value), dragStep = Number($("timelineStep").value);
  if (!SCALES.includes(visibleHours) || !DRAG_STEPS.includes(dragStep)) { $("timelineError").textContent = "请选择有效的比例尺和步进。"; return; }
  const wrap = document.querySelector(".planner-wrap");
  const position = start === state.timelineStart && end === state.timelineEnd ? wrap.scrollTop / hourHeight : 0;
  Object.assign(state, { timelineStart: start, timelineEnd: end, visibleHours, dragStep });
  const saved = save(); render();
  wrap.scrollTop = position * hourHeight;
  if (saved) closeDialog("timelineDialog");
  else $("timelineError").textContent = "设置已应用，但缓存保存失败；刷新后可能丢失。";
});
$("deleteTask").onclick = () => {
  if (!confirm("删除这个步骤？")) return;
  state.tasks = state.tasks.filter(t => t.id !== $("taskId").value);
  closeDialog("taskDialog"); save(); render();
};
$("resetDemo").onclick = () => {
  if (!confirm("导入示例会替换当前排程。是否继续？")) return;
  const next = { ...structuredClone(demo), timelineStart: "10:00", timelineEnd: "17:00", dishes: [] };
  next.tasks.forEach(t => {
    let dish = next.dishes.find(d => d.name === t.dish);
    if (!dish) { dish = { id: `d${crypto.randomUUID()}`, name: t.dish }; next.dishes.push(dish); }
    t.dishId = dish.id;
  });
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); }
  catch { storageWarning = "示例导入失败，当前排程未更改"; updateSaveStatus(); return; }
  state = next; storageWarning = ""; selectedDishId = null; filter = "all";
  document.querySelectorAll(".filter").forEach(b => b.classList.toggle("active", b.dataset.filter === "all"));
  closeDialog("helpDialog"); render();
  const wrap = document.querySelector(".planner-wrap"); wrap.scrollTop = 0; wrap.scrollLeft = 0;
};
// Duration steps remain pending until the user accepts a concrete proposal.
function scheduleBounds(task, plan) {
  const index = plan.findIndex(t => t.id === task.id);
  const earlier = plan.slice(0, index).filter(t => t.dishId === task.dishId);
  if (earlier.some(t => !isScheduled(t))) return null;
  const later = plan.slice(index + 1).filter(t => t.dishId === task.dishId && isScheduled(t));
  return {
    start: Math.max(minutes(state.timelineStart), ...earlier.map(t => minutes(t.end))),
    end: Math.min(minutes(state.timelineEnd), ...later.map(t => minutes(t.start)))
  };
}
function slotAvailable(task, start, end, plan) {
  for (const id of task.appliances) {
    const resource = state.appliances.find(a => a.id === id);
    if (!resource?.capacity) continue;
    const others = plan.filter(t => t.id !== task.id && isScheduled(t) && t.appliances.includes(id) && minutes(t.start) < end && minutes(t.end) > start);
    const boundaries = [start, ...others.map(t => minutes(t.start)).filter(t => t > start && t < end)];
    for (const time of boundaries) {
      const dishes = new Set(others.filter(t => minutes(t.start) <= time && minutes(t.end) > time).map(t => t.dishId));
      dishes.add(task.dishId);
      if (dishes.size > resource.capacity) return false;
    }
  }
  return true;
}
function findScheduleSlot(task, plan) {
  const bounds = scheduleBounds(task, plan);
  if (!bounds) return null;
  for (let start = bounds.start; start + task.duration <= bounds.end; start++) {
    if (slotAvailable(task, start, start + task.duration, plan)) return { start, end: start + task.duration };
  }
  return null;
}
function placeScheduledTask(plan, id, slot) {
  const task = plan.find(t => t.id === id);
  Object.assign(task, { start: addMinutes("00:00", slot.start), end: addMinutes("00:00", slot.end), scheduled: true });
}
function scheduleProposals(id) {
  const task = state.tasks.find(t => t.id === id);
  const baselineSlot = findScheduleSlot(task, state.tasks);
  const baseline = baselineSlot ? structuredClone(state.tasks) : null;
  if (baseline) placeScheduledTask(baseline, id, baselineSlot);
  const flexible = state.tasks.filter(t => t.id !== id && t.dishId !== task.dishId && t.timingMode === "duration" && !t.done && isScheduled(t)
    && minutes(t.start) >= minutes(state.timelineStart) && minutes(t.end) <= minutes(state.timelineEnd));
  if (!flexible.length) return { baseline, optimized: null, changes: [] };
  const optimized = structuredClone(state.tasks);
  const flexibleIds = new Set(flexible.map(t => t.id));
  optimized.forEach(t => { if (flexibleIds.has(t.id) || t.id === id) t.scheduled = false; });
  const changes = [];
  for (const original of flexible) {
    const candidate = optimized.find(t => t.id === original.id);
    const slot = findScheduleSlot(candidate, optimized);
    // An optimization may make another dish earlier, never later.
    if (!slot || slot.start > minutes(original.start)) return { baseline, optimized: null, changes: [] };
    placeScheduledTask(optimized, original.id, slot);
    if (slot.start !== minutes(original.start)) changes.push({ before: original, after: { ...candidate } });
  }
  const optimizedTask = optimized.find(t => t.id === id);
  const slot = findScheduleSlot(optimizedTask, optimized);
  if (!changes.length || !slot || baselineSlot && slot.start > baselineSlot.start) return { baseline, optimized: null, changes: [] };
  placeScheduledTask(optimized, id, slot);
  return { baseline, optimized, changes };
}
let pendingScheduling = null;
function resetScheduleResults() {
  pendingScheduling = null;
  $("scheduleResult").hidden = true;
  $("optimizationPreview").hidden = true;
  $("applySchedule").hidden = true;
  $("applyOptimized").hidden = true;
  $("scheduleStatus").textContent = "";
}
function openScheduling(id) {
  const task = state.tasks.find(t => t.id === id);
  if (!task || task.done || task.timingMode !== "duration") return;
  resetScheduleResults();
  $("scheduleDialog").dataset.taskId = id;
  $("skipSchedule").textContent = isScheduled(task) ? "保持原时间" : "暂不分配";
  $("scheduleIntro").textContent = `${task.duration} 分钟，在 ${state.timelineStart}–${state.timelineEnd} 内按器具和人力容量查找；确认前不会调整排程。`;
  $("scheduleDialog").showModal();
}
$("findSchedule").onclick = () => {
  resetScheduleResults();
  const id = $("scheduleDialog").dataset.taskId;
  const task = state.tasks.find(t => t.id === id);
  if (!task) return;
  let saved;
  try { saved = localStorage.getItem(STORAGE_KEY); } catch { $("scheduleStatus").textContent = "无法读取缓存，暂不能应用自动排程。"; return; }
  if (storageWarning) { $("scheduleStatus").textContent = "请先解决保存问题；当前新内容尚未保存，请勿刷新。"; return; }
  const snapshot = JSON.stringify(state);
  if (saved !== snapshot) { $("scheduleStatus").textContent = "排程缓存已变化，请刷新页面后重试。"; return; }
  if (!scheduleBounds(task, state.tasks)) { $("scheduleStatus").textContent = "请先安排本菜前面的待排程步骤。"; return; }
  const proposal = scheduleProposals(id);
  pendingScheduling = { ...proposal, id, snapshot, saved };
  if (proposal.baseline) {
    const candidate = proposal.baseline.find(t => t.id === id);
    $("scheduleResult").textContent = `可安排为 ${candidate.start}–${candidate.end}，不调整其他步骤。`;
    $("scheduleResult").hidden = false;
    $("applySchedule").hidden = false;
  }
  if (proposal.optimized) {
    const candidate = proposal.optimized.find(t => t.id === id);
    $("optimizationChanges").innerHTML = proposal.changes.map(({ before, after }) => `<li><strong>${esc(display(before.dish, "未命名菜品"))} · ${esc(display(before.name, "未命名步骤"))}</strong><br>${before.start}–${before.end} → ${after.start}–${after.end}</li>`).join("");
    $("optimizedResult").textContent = `调整后，本步骤可安排为 ${candidate.start}–${candidate.end}。固定时间和已完成步骤保持原位。`;
    $("optimizationPreview").hidden = false;
    $("applyOptimized").hidden = false;
  }
  if (!proposal.baseline && !proposal.optimized) $("scheduleStatus").textContent = "时间范围内没有可用空档。可延长时间范围，或检查所选器具和人力的容量。";
};
function applyScheduleProposal(optimized) {
  if (!pendingScheduling) return;
  const proposal = pendingScheduling;
  const tasks = optimized ? proposal.optimized : proposal.baseline;
  if (!tasks) return;
  try {
    if (JSON.stringify(state) !== proposal.snapshot || localStorage.getItem(STORAGE_KEY) !== proposal.saved) {
      $("scheduleStatus").textContent = "排程已变化，请重新查找；其他页面修改后请先刷新。"; return;
    }
    const next = { ...state, tasks };
    if (!validState(next)) throw new Error("Invalid schedule");
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    state = next;
  } catch { $("scheduleStatus").textContent = "无法保存自动排程，原排程未调整。"; return; }
  pendingScheduling = null; storageWarning = ""; filter = "all";
  document.querySelectorAll(".filter").forEach(b => b.classList.toggle("active", b.dataset.filter === "all"));
  closeDialog("scheduleDialog"); render();
}
$("applySchedule").onclick = () => applyScheduleProposal(false);
$("applyOptimized").onclick = () => applyScheduleProposal(true);

// Compact, versioned, compressed clipboard format. All processing stays in the browser.
function packPlan(plan) {
  const resources = new Map(plan.appliances.map((a, i) => [a.id, i]));
  const dishes = new Map(plan.dishes.map((d, i) => [d.id, i]));
  return [3, minutes(plan.timelineStart), minutes(plan.timelineEnd), plan.visibleHours || 2.5, plan.dragStep || 5,
    plan.appliances.map(a => [a.name, a.icon, a.width || 0, a.capacity || 0]),
    plan.dishes.map(d => d.name),
    plan.tasks.map(t => [t.name, dishes.get(t.dishId), minutes(t.start), minutes(t.end), t.appliances.map(id => resources.get(id)), t.note, t.done ? 1 : 0, t.timingMode === "duration" ? t.duration : 0, isScheduled(t) ? 1 : 0]), plan.unassignedWidth || 0];
}
function unpackPlan(data) {
  const bad = () => { throw new Error("传输文本的内容不完整或格式不正确"); };
  if (!Array.isArray(data) || !(data[0] === 1 && data.length === 8 || [2, 3].includes(data[0]) && data.length === 9)) return bad();
  const [, start, end, visibleHours, dragStep, resources, dishes, tasks, unassignedWidth = 0] = data;
  if (!Number.isFinite(unassignedWidth) || unassignedWidth !== 0 && (unassignedWidth < MIN_COLUMN_WIDTH || unassignedWidth > MAX_COLUMN_WIDTH)) return bad();
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end > 1439 || start >= end || !SCALES.includes(visibleHours) || !DRAG_STEPS.includes(dragStep)) return bad();
  if (!Array.isArray(resources) || resources.length > 1000 || !Array.isArray(dishes) || dishes.length > 5000 || !dishes.every(d => typeof d === "string") || !Array.isArray(tasks) || tasks.length > 20000) return bad();
  if (!resources.every(a => Array.isArray(a) && a.length === 4 && typeof a[0] === "string" && typeof a[1] === "string" && Number.isFinite(a[2]) && (a[2] === 0 || a[2] >= MIN_COLUMN_WIDTH && a[2] <= MAX_COLUMN_WIDTH) && [0, 1, 2, 3].includes(a[3]))) return bad();
  if (!tasks.every(t => Array.isArray(t) && t.length === (data[0] === 3 ? 9 : 7) && typeof t[0] === "string" && Number.isInteger(t[1]) && t[1] >= 0 && t[1] < dishes.length && Number.isInteger(t[2]) && Number.isInteger(t[3]) && t[2] >= 0 && t[3] <= 1439 && t[2] < t[3] && Array.isArray(t[4]) && new Set(t[4]).size === t[4].length && t[4].every(i => Number.isInteger(i) && i >= 0 && i < resources.length) && typeof t[5] === "string" && [0, 1].includes(t[6]))) return bad();
  if (data[0] === 3 && !tasks.every(t => Number.isInteger(t[7]) && t[7] >= 0 && t[7] <= 1439 && [0, 1].includes(t[8]) && (t[7] ? t[3] - t[2] === t[7] && !(t[6] && !t[8]) : t[8] === 1))) return bad();
  const plan = {
    resourceIconVersion: 1, timelineStart: addMinutes("00:00", start), timelineEnd: addMinutes("00:00", end), visibleHours, dragStep, ...(unassignedWidth ? { unassignedWidth } : {}),
    appliances: resources.map(a => ({ id: `a${crypto.randomUUID()}`, name: a[0], icon: a[1], ...(a[2] ? { width: a[2] } : {}), capacity: a[3] })),
    dishes: dishes.map(name => ({ id: `d${crypto.randomUUID()}`, name }))
  };
  plan.tasks = tasks.map(t => ({ id: `t${crypto.randomUUID()}`, name: t[0], dishId: plan.dishes[t[1]].id, dish: dishes[t[1]], start: addMinutes("00:00", t[2]), end: addMinutes("00:00", t[3]), appliances: t[4].map(i => plan.appliances[i].id), note: t[5], done: Boolean(t[6]), ...(data[0] === 3 && t[7] ? { timingMode: "duration", duration: t[7], scheduled: Boolean(t[8]) } : {}) }));
  if (!validState(plan)) return bad();
  return plan;
}
const crcTable = Array.from({ length: 256 }, (_, i) => {
  let crc = i;
  for (let bit = 0; bit < 8; bit++) crc = crc & 1 ? 0xedb88320 ^ crc >>> 1 : crc >>> 1;
  return crc >>> 0;
});
function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = crcTable[(crc ^ byte) & 255] ^ crc >>> 8;
  return (crc ^ 0xffffffff) >>> 0;
}
function encodePlan(plan) {
  if (!globalThis.fflate) throw new Error("压缩组件未加载，请刷新页面后重试。");
  const raw = new TextEncoder().encode(JSON.stringify(packPlan(plan)));
  if (raw.length > 1048576) throw new Error("排程过大，暂无法生成传输文本");
  const compressed = fflate.gzipSync(raw, { level: 9, mtime: 0 });
  let binary = "";
  for (const byte of compressed) binary += String.fromCharCode(byte);
  const token = "MC1." + btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  if (token.length > 200000) throw new Error("排程过大，暂无法生成传输文本");
  return token;
}
async function decodePlan(text) {
  if (!globalThis.fflate) throw new Error("压缩组件未加载，请刷新页面后重试。");
  const token = text.replace(/\s/g, "");
  if (token.length > 200000 || !/^MC1\.[A-Za-z0-9_-]+$/.test(token)) throw new Error("请粘贴完整的 MC1. 排程文本");
  try {
    const base64 = token.slice(4).replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(base64 + "=".repeat((4 - base64.length % 4) % 4)), c => c.charCodeAt(0));
    if (bytes.length < 18 || bytes[0] !== 31 || bytes[1] !== 139 || bytes[2] !== 8) throw new Error("Invalid gzip");
    const trailer = new DataView(bytes.buffer, bytes.byteOffset + bytes.length - 8, 8);
    const expectedSize = trailer.getUint32(4, true);
    if (expectedSize > 1048576) throw new Error("Too large");
    const chunks = [];
    let size = 0;
    const decoder = new fflate.Gunzip(chunk => {
      size += chunk.length;
      if (size > 1048576) throw new Error("Too large");
      chunks.push(chunk.slice());
    });
    for (let offset = 0; offset < bytes.length; offset += 1024) {
      decoder.push(bytes.subarray(offset, offset + 1024), offset + 1024 >= bytes.length);
    }
    const buffer = new Uint8Array(size);
    let offset = 0;
    chunks.forEach(chunk => { buffer.set(chunk, offset); offset += chunk.length; });
    if (size !== expectedSize || crc32(buffer) !== trailer.getUint32(0, true)) throw new Error("Checksum mismatch");
    return unpackPlan(JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(buffer)));
  } catch {
    throw new Error("传输文本无效、已损坏或内容过大，请重新复制完整文本");
  }
}
let pendingImport = null;
function transferMessage(message, error = false) {
  $("transferStatus").textContent = message;
  $("transferStatus").classList.toggle("save-error", error);
}
$("openTransfer").onclick = () => {
  pendingImport = null;
  for (const id of ["exportText", "importText"]) $(id).value = "";
  $("confirmImport").hidden = true;
  $("importPreview").hidden = true;
  $("copyExport").disabled = true;
  transferMessage("");
  $("transferDialog").showModal();
};
async function copyExportText() {
  const token = $("exportText").value;
  if (!token) return;
  let copied = false;
  try { await navigator.clipboard.writeText(token); copied = true; }
  catch {
    $("exportText").focus(); $("exportText").select();
    $("exportText").setSelectionRange(0, token.length);
    try { copied = document.execCommand("copy"); } catch { /* Manual selection remains available. */ }
  }
  transferMessage(copied ? `已复制压缩文本（${token.length} 字符），可粘贴到另一台设备。` : `已生成压缩文本（${token.length} 字符），请长按或选中文本复制。`);
}
$("copyExport").onclick = copyExportText;
$("exportPlan").onclick = async () => {
  $("exportPlan").disabled = true;
  $("copyExport").disabled = true;
  $("exportText").value = "";
  try {
    $("exportText").value = encodePlan(state);
    $("copyExport").disabled = false;
    await copyExportText();
  } catch (error) { transferMessage(error.message, true); }
  finally { $("exportPlan").disabled = false; }
};
$("importText").oninput = () => {
  pendingImport = null;
  $("confirmImport").hidden = true;
  $("importPreview").hidden = true;
  transferMessage("");
};
$("previewImport").onclick = async () => {
  const text = $("importText").value;
  pendingImport = null;
  $("confirmImport").hidden = true;
  $("importPreview").hidden = true;
  $("previewImport").disabled = true;
  try {
    const plan = await decodePlan(text);
    if (text !== $("importText").value) { transferMessage("文本已改变，请重新检查。", true); return; }
    pendingImport = { plan, text };
    $("importPreview").textContent = `${plan.dishes.length} 道菜品、${plan.tasks.length} 个步骤、${plan.appliances.length} 个器具或人员。导入将替换当前排程，建议先复制导出文本作为备份。`;
    $("importPreview").hidden = false;
    $("confirmImport").hidden = false;
    transferMessage("内容检查通过，尚未替换当前排程。");
  } catch (error) { transferMessage(error.message, true); }
  finally { $("previewImport").disabled = false; }
};
$("confirmImport").onclick = () => {
  if (!pendingImport || pendingImport.text !== $("importText").value) return;
  const next = pendingImport.plan;
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); }
  catch { transferMessage("浏览器缓存无法保存，原排程未改动。请先备份或清理空间。", true); return; }
  state = next; pendingImport = null; selectedDishId = null; filter = "all"; storageWarning = "";
  document.querySelectorAll(".filter").forEach(button => button.classList.toggle("active", button.dataset.filter === "all"));
  closeDialog("transferDialog"); closeDialog("menuDialog"); render();
  const wrap = document.querySelector(".planner-wrap"); wrap.scrollTop = 0; wrap.scrollLeft = 0;
};

// Some mobile engines suppress the compatibility click after a column drag.
// Activate a stationary finger release once, and consume its later ghost click.
const touchButtons = new Map();
let recentTouchTaps = [];
document.addEventListener("pointerdown", event => {
  if (event.pointerType !== "touch" || !event.isPrimary) return;
  const button = event.target.closest?.("button:not(.column-move)");
  if (button && !button.disabled) touchButtons.set(event.pointerId, { button, x: event.clientX, y: event.clientY, moved: false });
}, true);
document.addEventListener("pointermove", event => {
  const tap = touchButtons.get(event.pointerId);
  if (tap && Math.hypot(event.clientX - tap.x, event.clientY - tap.y) > 8) tap.moved = true;
}, true);
document.addEventListener("pointercancel", event => touchButtons.delete(event.pointerId), true);
document.addEventListener("pointerup", event => {
  const tap = touchButtons.get(event.pointerId);
  touchButtons.delete(event.pointerId);
  if (!tap || tap.moved || !tap.button.isConnected || tap.button.disabled || event.target.closest?.("button") !== tap.button) return;
  event.preventDefault();
  recentTouchTaps = recentTouchTaps.filter(t => Date.now() - t.time < 750);
  recentTouchTaps.push({ x: event.clientX, y: event.clientY, time: Date.now() });
  tap.button.click();
}, true);
document.addEventListener("click", event => {
  if (!event.isTrusted || !event.detail || event.pointerType === "mouse") return;
  if (recentTouchTaps.some(t => Date.now() - t.time < 750 && Math.hypot(event.clientX - t.x, event.clientY - t.y) < 16)) {
    event.preventDefault(); event.stopImmediatePropagation();
  }
}, true);

window.addEventListener("resize", render);
render();
setInterval(updateNowLine, 30000);
