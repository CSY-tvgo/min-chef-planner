const STORAGE_KEY = "banquet-kitchen-plan-v1";
let hourHeight = 180;
const MIN_COLUMN_WIDTH = 64;
const MAX_COLUMN_WIDTH = 800;

const COLORS = ["#cfe7d4", "#f4d28a", "#eaa18f", "#c9c4e7", "#b6dce4"];
const demo = {
  appliances: [
    { id: "stove", name: "灶台", icon: "♨" }, { id: "oven", name: "烤箱", icon: "▱" },
    { id: "rice", name: "电饭锅", icon: "◌" }, { id: "steamer", name: "蒸锅", icon: "◉" }
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
  const ids = new Set();
  for (const a of value.appliances) {
    if (!a || typeof a.id !== "string" || ids.has(a.id) || typeof a.name !== "string" || typeof a.icon !== "string" || (a.width !== undefined && (!Number.isFinite(a.width) || a.width < MIN_COLUMN_WIDTH || a.width > MAX_COLUMN_WIDTH))) return false;
    ids.add(a.id);
  }
  const tasks = new Set();
  return value.tasks.every(t => {
    if (!t || typeof t.id !== "string" || tasks.has(t.id) || !validTime(t.start) || !validTime(t.end) || minutes(t.end) <= minutes(t.start) || !Array.isArray(t.appliances) || !t.appliances.every(id => ids.has(id)) || typeof t.name !== "string" || typeof t.dish !== "string" || typeof t.note !== "string" || typeof t.done !== "boolean") return false;
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
state.timelineStart ||= "10:00";
if (!state.timelineEnd && state.timelineStart === "23:59") state.timelineStart = "23:58";
// Old plans did not have an explicit end: retain their visible tasks on migration.
state.timelineEnd ||= addMinutes("00:00", Math.min(1439, Math.max(minutes(state.timelineStart) + 60, 17 * 60, ...state.tasks.map(t => minutes(t.end)))));
let filter = "all";
let suppressClickUntil = 0;
let timelineDuration = 0;
const $ = (id) => document.getElementById(id);
function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    storageWarning = "";
  } catch {
    storageWarning = "保存失败，请勿关闭页面";
  }
  $("saveState").textContent = storageWarning || "已自动保存";
  $("saveState").classList.toggle("save-error", Boolean(storageWarning));
}
function minutes(time) { const [h, m] = time.split(":").map(Number); return h * 60 + m; }
function esc(value) { return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[c])); }
function display(value, fallback) { return value || fallback; }
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
function sizeTimeline() {
  const wrap = document.querySelector(".planner-wrap");
  const height = Math.max(280, window.innerHeight - (wrap.getBoundingClientRect().top + window.scrollY) - 20);
  wrap.style.height = `${height}px`;
  hourHeight = (height - 64) / 2.5;
  $("planner").style.setProperty("--hour", `${hourHeight}px`);
}
function render() {
  const start = minutes(state.timelineStart);
  sizeTimeline();
  const end = minutes(state.timelineEnd);
  timelineDuration = end - start;
  $("planner").style.setProperty("--timeline-height", `${timelineDuration / 60 * hourHeight}px`);
  const visible = state.tasks.filter(t => (filter === "all" || (filter === "done" ? t.done : !t.done)) && minutes(t.end) > start && minutes(t.start) < end);
  const layouts = state.appliances.map(a => layoutTasks(visible.filter(t => t.appliances.includes(a.id))));
  const defaultWidth = Math.max(MIN_COLUMN_WIDTH, (document.querySelector(".planner-wrap").clientWidth - 28) / 4);
  const widths = state.appliances.map(a => a.width || defaultWidth);
  $("planner").style.width = `calc(var(--sidebar) + ${widths.reduce((a, b) => a + b, 0)}px)`;
  $("applianceHeads").innerHTML = state.appliances.map((a, i) => `<div class="appliance-head" style="flex-basis:${widths[i]}px"><span class="tool-icon">${esc(a.icon)}</span><strong>${esc(display(a.name, "未命名器具"))}</strong><small>${state.tasks.filter(t => t.appliances.includes(a.id)).length} 个步骤</small><button class="delete-appliance" data-delete-appliance="${esc(a.id)}" aria-label="删除${esc(display(a.name, "未命名器具"))}">×</button><span class="column-resize" data-resize-appliance="${esc(a.id)}" role="separator" tabindex="0" aria-label="调整${esc(display(a.name, "未命名器具"))}列宽" aria-orientation="vertical" aria-valuemin="${MIN_COLUMN_WIDTH}" aria-valuemax="${MAX_COLUMN_WIDTH}" aria-valuenow="${Math.round(widths[i])}"></span></div>`).join("");
  const firstHour = Math.ceil(start / 60) * 60;
  $("timeAxis").innerHTML = Array.from({ length: Math.max(0, Math.ceil((end - firstHour) / 60)) }, (_, index) => {
    const time = firstHour + index * 60;
    return `<div class="time-label" style="top:${(time - start) / 60 * hourHeight}px">${Math.floor(time / 60)}</div>`;
  }).join("");
  $("lanes").style.backgroundPositionY = `${(firstHour - start) / 60 * hourHeight}px`;
  $("lanes").innerHTML = state.appliances.map((a, i) => `<div class="lane" style="flex-basis:${widths[i]}px">${visible.filter(t => t.appliances.includes(a.id)).map(t => taskCard(t, layouts[i])).join("")}</div>`).join("");
  const dishes = new Set(state.tasks.map(t => display(t.dish, "未命名菜品")));
  $("summary").innerHTML = `<div class="stat"><strong>${dishes.size}</strong><span>道菜品</span></div><div class="stat"><strong>${state.appliances.length}</strong><span>件器具</span></div><div class="stat"><strong>${state.tasks.filter(t => t.done).length}/${state.tasks.length}</strong><span>步骤完成</span></div>`;
  $("menuList").innerHTML = state.tasks.map(t => `<button type="button" class="menu-item" data-edit-task="${esc(t.id)}"><strong>${esc(display(t.dish, "未命名菜品"))} · ${esc(display(t.name, "未命名步骤"))}</strong><span>${t.start}–${t.end}${t.appliances.length ? "" : " · 未分配器具"}</span></button>`).join("") || "暂无步骤";
  document.querySelectorAll("[data-edit-task]").forEach(b => b.onclick = () => { closeDialog("menuDialog"); openTask(b.dataset.editTask); });
  document.querySelectorAll("[data-delete-appliance]").forEach(b => b.onclick = () => deleteAppliance(b.dataset.deleteAppliance));
  document.querySelectorAll(".task-card").forEach(card => {
    card.onclick = (event) => { if (Date.now() > suppressClickUntil && !event.target.closest(".resize-handle, .move-handle")) openTask(card.dataset.id); };
    card.querySelector(".check").onclick = (event) => {
      event.stopPropagation();
      const task = state.tasks.find(t => t.id === card.dataset.id);
      if (task) { task.done = !task.done; save(); render(); }
    };
    card.querySelectorAll(".resize-handle, .move-handle").forEach(handle => handle.addEventListener("pointerdown", startResize));
  });
  $("saveState").textContent = storageWarning || "已自动保存";
  $("saveState").classList.toggle("save-error", Boolean(storageWarning));
  document.querySelectorAll("[data-resize-appliance]").forEach(handle => {
    handle.addEventListener("pointerdown", startColumnResize);
    handle.addEventListener("keydown", e => {
      if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
      e.preventDefault();
      const a = state.appliances.find(a => a.id === handle.dataset.resizeAppliance);
      a.width = Math.max(MIN_COLUMN_WIDTH, Math.min(MAX_COLUMN_WIDTH, handle.parentElement.getBoundingClientRect().width + (e.key === "ArrowRight" ? 10 : -10)));
      save(); render();
      document.querySelectorAll("[data-resize-appliance]").forEach(next => { if (next.dataset.resizeAppliance === a.id) next.focus(); });
    });
  });
  updateNowLine();
}
function taskCard(task, layout) {
  const top = Math.max(0, (minutes(task.start) - minutes(state.timelineStart)) / 60 * hourHeight);
  const height = (Math.min(minutes(task.end), minutes(state.timelineEnd)) - Math.max(minutes(task.start), minutes(state.timelineStart))) / 60 * hourHeight;
  const { column, count } = layout.get(task.id);
  const index = state.tasks.findIndex(t => t.id === task.id);
  const title = `${display(task.name, "未命名步骤")} · ${display(task.dish, "未命名菜品")} ${task.start}–${task.end}`;
  return `<article class="task-card ${height < 48 ? "short" : ""} ${task.done ? "done" : ""}" data-id="${esc(task.id)}" title="${esc(title)}" style="top:${top}px;height:${height}px;left:calc(${column / count * 100}% + ${count > 1 ? 1 : 4}px);width:calc(${100 / count}% - ${count > 1 ? 2 : 8}px);background:${COLORS[index % COLORS.length]}"><span class="resize-handle top" data-edge="start" title="拖动调整开始时间"></span><button type="button" class="move-handle" data-edge="move" aria-label="拖动移动步骤">⠿</button><button type="button" class="check" aria-label="${task.done ? "标为待处理" : "标为完成"}">${task.done ? "✓" : ""}</button><strong>${esc(display(task.name, "未命名步骤"))}</strong><small>${task.start}–${task.end} · ${esc(display(task.dish, "未命名菜品"))}${task.note ? ` · ${esc(task.note)}` : ""}</small><span class="resize-handle bottom" data-edge="end" title="拖动调整结束时间"></span></article>`;
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
  const minimumDuration = Math.min(5, initialEnd - initialStart);
  const boundDelta = (delta, min, max) => Math.max(Math.ceil(min / 5) * 5, Math.min(Math.floor(max / 5) * 5, delta));
  const pointerId = event.pointerId;
  const planner = $("planner");
  planner.setPointerCapture(pointerId);
  const move = (e) => {
    if (e.pointerId !== pointerId) return;
    const delta = Math.round((e.clientY - initialY) / dragScale * 60 / 5) * 5;
    if (edge === "move") {
      const shift = boundDelta(delta, -initialStart, 1439 - initialEnd);
      task.start = addMinutes("00:00", initialStart + shift);
      task.end = addMinutes("00:00", initialEnd + shift);
    } else if (edge === "start") {
      task.start = addMinutes("00:00", initialStart + boundDelta(delta, -initialStart, initialEnd - minimumDuration - initialStart));
    } else {
      task.end = addMinutes("00:00", initialEnd + boundDelta(delta, initialStart + minimumDuration - initialEnd, 1439 - initialEnd));
    }
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
    }
    suppressClickUntil = Date.now() + 400;
    save(); render();
  };
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", finish);
  document.addEventListener("pointercancel", finish);
}
function startColumnResize(event) {
  if (!event.isPrimary || event.button !== 0) return;
  event.preventDefault();
  const appliance = state.appliances.find(a => a.id === event.currentTarget.dataset.resizeAppliance);
  const originalWidth = appliance.width;
  const initialWidth = event.currentTarget.parentElement.getBoundingClientRect().width;
  const initialX = event.clientX, pointerId = event.pointerId;
  const planner = $("planner");
  planner.setPointerCapture(pointerId);
  const move = e => {
    if (e.pointerId !== pointerId) return;
    appliance.width = Math.max(MIN_COLUMN_WIDTH, Math.min(MAX_COLUMN_WIDTH, initialWidth + e.clientX - initialX));
    render();
  };
  const finish = e => {
    if (e.pointerId !== pointerId) return;
    document.removeEventListener("pointermove", move);
    document.removeEventListener("pointerup", finish);
    document.removeEventListener("pointercancel", finish);
    if (planner.hasPointerCapture(pointerId)) planner.releasePointerCapture(pointerId);
    if (e.type === "pointercancel") {
      if (originalWidth === undefined) delete appliance.width;
      else appliance.width = originalWidth;
    }
    save(); render();
  };
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", finish);
  document.addEventListener("pointercancel", finish);
}
function openTask(id = "") {
  const task = state.tasks.find(t => t.id === id);
  $("taskDialogTitle").textContent = task ? "编辑烹饪步骤" : "添加烹饪步骤";
  $("taskId").value = id; $("taskName").value = task?.name || ""; $("taskDish").value = task?.dish || ""; $("taskStart").value = task?.start || state.timelineStart; $("taskEnd").value = task?.end || addMinutes("00:00", Math.min(1439, minutes(state.timelineStart) + 60)); $("taskNote").value = task?.note || "";
  $("applianceChecks").innerHTML = state.appliances.map(a => `<label class="check-item"><input type="checkbox" value="${esc(a.id)}" ${task?.appliances.includes(a.id) ? "checked" : ""}>${esc(a.icon)} ${esc(display(a.name, "未命名器具"))}</label>`).join("");
  $("deleteTask").hidden = !task;
  $("taskDialog").showModal();
}
function closeDialog(id) {
  const dialog = $(id);
  if (dialog?.open) dialog.close();
}
function deleteAppliance(id) {
  if (!confirm("删除器具后，关联步骤将失去该器具。确定删除吗？")) return;
  state.appliances = state.appliances.filter(a => a.id !== id); state.tasks.forEach(t => t.appliances = t.appliances.filter(a => a !== id)); save(); render();
}
document.querySelectorAll(".filter").forEach(b => b.onclick = () => { filter = b.dataset.filter; document.querySelectorAll(".filter").forEach(x => x.classList.toggle("active", x === b)); render(); });
$("addTaskTop").onclick = () => openTask(); $("addAppliance").onclick = () => $("applianceDialog").showModal(); $("manageMenu").onclick = () => $("menuDialog").showModal();
$("setTimelineStart").onclick = () => { $("timelineStart").value = state.timelineStart; $("timelineEnd").value = state.timelineEnd; $("timelineError").textContent = ""; $("timelineDialog").showModal(); };
document.querySelectorAll("[data-close-dialog]").forEach(button => button.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); closeDialog(button.dataset.closeDialog); }));
document.querySelectorAll("dialog").forEach(dialog => dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); }));
$("taskForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const id = $("taskId").value || `t${crypto.randomUUID()}`;
  const name = $("taskName").value.trim();
  const dish = $("taskDish").value.trim();
  const start = $("taskStart").value;
  const end = $("taskEnd").value;
  const appliances = [...$("applianceChecks").querySelectorAll("input:checked")].map(x => x.value);
  const data = { id, name, dish, start, end, appliances, note: $("taskNote").value.trim(), done: state.tasks.find(t => t.id === id)?.done || false };
  if (!start || !end || minutes(end) <= minutes(start)) return alert("结束时间必须晚于开始时间。");
  const index = state.tasks.findIndex(t => t.id === id);
  index >= 0 ? state.tasks.splice(index, 1, data) : state.tasks.push(data);
  closeDialog("taskDialog"); save(); render();
});
$("applianceForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const name = $("applianceName").value.trim();
  state.appliances.push({ id: `a${crypto.randomUUID()}`, name, icon: $("applianceIcon").value });
  $("applianceForm").reset(); closeDialog("applianceDialog"); save(); render();
});
$("timelineForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const start = $("timelineStart").value, end = $("timelineEnd").value;
  if (!validTime(start) || !validTime(end) || minutes(end) <= minutes(start)) {
    $("timelineError").textContent = "结束时间必须晚于起始时间";
    return;
  }
  state.timelineStart = start;
  state.timelineEnd = end;
  closeDialog("timelineDialog"); save(); render();
});
$("deleteTask").onclick = () => {
  if (!confirm("删除这个步骤？")) return;
  state.tasks = state.tasks.filter(t => t.id !== $("taskId").value);
  closeDialog("taskDialog"); save(); render();
};
$("resetDemo").onclick = () => { if (confirm("恢复示例排程？当前数据会被覆盖。")) { state = structuredClone(demo); state.timelineStart = "10:00"; state.timelineEnd = "17:00"; save(); render(); } };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") document.querySelectorAll("dialog[open]").forEach(d => d.close()); });
window.addEventListener("resize", render);
render();
setInterval(updateNowLine, 30000);
