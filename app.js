const STORAGE_KEY = "banquet-kitchen-plan-v1";
const HOUR_HEIGHT = 88;
const HOUR_COUNT = 7;
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
let state;
try {
  state = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null") || structuredClone(demo);
} catch {
  state = structuredClone(demo);
}
state.timelineStart ||= "10:00";
let filter = "all";
const $ = (id) => document.getElementById(id);
function save() { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); $("saveState").innerHTML = '<span class="status-dot"></span>已自动保存'; }
function minutes(time) { const [h, m] = time.split(":").map(Number); return h * 60 + m; }
function esc(value) { return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[c])); }
function display(value, fallback) { return value || fallback; }
function addMinutes(time, amount) {
  const value = minutes(time) + amount;
  const hours = Math.floor((value + 1440) % 1440 / 60);
  const mins = (value + 1440) % 60;
  return `${String(hours).padStart(2, "0")}:${String(mins).padStart(2, "0")}`;
}
function render() {
  $("applianceHeads").innerHTML = state.appliances.map((a) => `<div class="appliance-head"><span class="tool-icon">${a.icon}</span><strong>${esc(display(a.name, "未命名器具"))}</strong><small>${state.tasks.filter(t => t.appliances.includes(a.id)).length} 个步骤</small><button class="delete-appliance" data-delete-appliance="${a.id}" title="删除器具">×</button></div>`).join("");
  $("timeAxis").innerHTML = Array.from({ length: HOUR_COUNT }, (_, index) => `<div class="time-label">${addMinutes(state.timelineStart, index * 60)}</div>`).join("");
  const visible = state.tasks.filter(t => filter === "all" || (filter === "done" ? t.done : !t.done));
  $("lanes").innerHTML = state.appliances.map((a) => `<div class="lane">${visible.filter(t => t.appliances.includes(a.id)).map(taskCard).join("")}</div>`).join("");
  const dishes = new Set(state.tasks.map(t => display(t.dish, "未命名菜品")));
  $("summary").innerHTML = `<div class="stat"><strong>${dishes.size}</strong><span>道菜品</span></div><div class="stat"><strong>${state.appliances.length}</strong><span>件器具</span></div><div class="stat"><strong>${state.tasks.filter(t => t.done).length}/${state.tasks.length}</strong><span>步骤完成</span></div>`;
  $("menuList").innerHTML = [...dishes].map(d => `<div class="menu-item"><strong>${esc(d)}</strong><span>${state.tasks.filter(t => display(t.dish, "未命名菜品") === d).length} 个步骤</span></div>`).join("");
  document.querySelectorAll("[data-delete-appliance]").forEach(b => b.onclick = () => deleteAppliance(b.dataset.deleteAppliance));
  document.querySelectorAll(".task-card").forEach(card => {
    card.onclick = () => openTask(card.dataset.id);
    card.querySelector(".check").onclick = (event) => {
      event.stopPropagation();
      const task = state.tasks.find(t => t.id === card.dataset.id);
      if (task) { task.done = !task.done; save(); render(); }
    };
    card.querySelectorAll(".resize-handle").forEach(handle => handle.addEventListener("pointerdown", startResize));
  });
  updateNowLine();
}
function taskCard(task) {
  const top = (minutes(task.start) - minutes(state.timelineStart)) / 60 * HOUR_HEIGHT + 3;
  const height = Math.max(54, (minutes(task.end) - minutes(task.start)) / 60 * HOUR_HEIGHT - 5);
  const index = state.tasks.findIndex(t => t.id === task.id);
  const conflict = task.appliances.some(a => state.tasks.some(other => other.id !== task.id && other.appliances.includes(a) && minutes(other.start) < minutes(task.end) && minutes(other.end) > minutes(task.start)));
  return `<article class="task-card ${task.done ? "done" : ""} ${conflict ? "conflict" : ""}" data-id="${task.id}" style="top:${top}px;height:${height}px;background:${COLORS[index % COLORS.length]}"><span class="resize-handle top" data-edge="start"></span><span class="check">${task.done ? "✓" : ""}</span><strong>${esc(display(task.name, "未命名步骤"))}</strong><small>${esc(display(task.dish, "未命名菜品"))}${task.note ? ` · ${esc(task.note)}` : ""}</small><span class="resize-handle bottom" data-edge="end"></span></article>`;
}
function updateNowLine() {
  const now = new Date();
  const current = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
  const offset = current - minutes(state.timelineStart);
  const line = $("nowLine");
  line.style.top = `${Math.max(0, Math.min(HOUR_COUNT * HOUR_HEIGHT, offset / 60 * HOUR_HEIGHT))}px`;
  line.hidden = offset < 0 || offset > HOUR_COUNT * 60;
}
function startResize(event) {
  event.preventDefault();
  event.stopPropagation();
  const card = event.currentTarget.closest(".task-card");
  const task = state.tasks.find(t => t.id === card.dataset.id);
  const edge = event.currentTarget.dataset.edge;
  if (!task) return;
  const initialY = event.clientY;
  const initialTime = edge === "start" ? task.start : task.end;
  const initialMinutes = minutes(initialTime);
  const move = (moveEvent) => {
    const delta = Math.round((moveEvent.clientY - initialY) / HOUR_HEIGHT * 60 / 15) * 15;
    const value = addMinutes(state.timelineStart, initialMinutes - minutes(state.timelineStart) + delta);
    if (edge === "start" && minutes(value) < minutes(task.end) - 15) task.start = value;
    if (edge === "end" && minutes(value) > minutes(task.start) + 15) task.end = value;
    render();
  };
  const finish = () => { document.removeEventListener("pointermove", move); document.removeEventListener("pointerup", finish); save(); };
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", finish, { once: true });
}
function openTask(id = "") {
  const task = state.tasks.find(t => t.id === id);
  $("taskDialogTitle").textContent = task ? "编辑烹饪步骤" : "添加烹饪步骤";
  $("taskId").value = id; $("taskName").value = task?.name || ""; $("taskDish").value = task?.dish || ""; $("taskStart").value = task?.start || state.timelineStart; $("taskEnd").value = task?.end || addMinutes(state.timelineStart, 60); $("taskNote").value = task?.note || "";
  $("applianceChecks").innerHTML = state.appliances.map(a => `<label class="check-item"><input type="checkbox" value="${a.id}" ${task?.appliances.includes(a.id) ? "checked" : ""}>${a.icon} ${esc(a.name)}</label>`).join("");
  $("taskDialog").showModal();
}
function closeDialog(id) {
  const dialog = $(id);
  if (dialog?.open) dialog.close();
}
function deleteAppliance(id) {
  if (state.appliances.length <= 1) return alert("至少需要保留一件器具。");
  if (!confirm("删除器具后，关联步骤将失去该器具。确定删除吗？")) return;
  state.appliances = state.appliances.filter(a => a.id !== id); state.tasks.forEach(t => t.appliances = t.appliances.filter(a => a !== id)); save(); render();
}
document.querySelectorAll(".filter").forEach(b => b.onclick = () => { filter = b.dataset.filter; document.querySelectorAll(".filter").forEach(x => x.classList.toggle("active", x === b)); render(); });
$("addTaskTop").onclick = () => openTask(); $("addAppliance").onclick = () => $("applianceDialog").showModal(); $("manageMenu").onclick = () => $("menuDialog").showModal();
$("setTimelineStart").onclick = () => { $("timelineStart").value = state.timelineStart; $("timelineDialog").showModal(); };
document.querySelectorAll("[data-close-dialog]").forEach(button => button.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); closeDialog(button.dataset.closeDialog); }));
document.querySelectorAll("dialog").forEach(dialog => dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); }));
$("taskForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const id = $("taskId").value || `t${Date.now()}`;
  const name = $("taskName").value.trim();
  const dish = $("taskDish").value.trim();
  const start = $("taskStart").value;
  const end = $("taskEnd").value;
  const appliances = [...$("applianceChecks").querySelectorAll("input:checked")].map(x => x.value);
  if (!appliances.length) return alert("请选择至少一件器具。");
  const data = { id, name, dish, start, end, appliances, note: $("taskNote").value.trim(), done: state.tasks.find(t => t.id === id)?.done || false };
  if (!start || !end || minutes(end) <= minutes(start)) return alert("结束时间必须晚于开始时间。");
  const index = state.tasks.findIndex(t => t.id === id);
  index >= 0 ? state.tasks.splice(index, 1, data) : state.tasks.push(data);
  closeDialog("taskDialog"); save(); render();
});
$("applianceForm").addEventListener("submit", (e) => {
  e.preventDefault();
  const name = $("applianceName").value.trim();
  state.appliances.push({ id: `a${Date.now()}`, name, icon: $("applianceIcon").value });
  $("applianceForm").reset(); closeDialog("applianceDialog"); save(); render();
});
$("timelineForm").addEventListener("submit", (e) => {
  e.preventDefault();
  if (!$("timelineStart").value) return;
  state.timelineStart = $("timelineStart").value;
  closeDialog("timelineDialog"); save(); render();
});
$("resetDemo").onclick = () => { if (confirm("恢复示例排程？当前数据会被覆盖。")) { state = structuredClone(demo); state.timelineStart = "10:00"; save(); render(); } };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") document.querySelectorAll("dialog[open]").forEach(d => d.close()); });
render();
setInterval(updateNowLine, 30000);
