<template>
  <main>
    <h1>光伏组串IV扫描台</h1>
    <div v-if="!session">
      <p class="sub">扫描员提交开路电压、短路电流与填充因子；通知通道叫醒工人出结论。登录框已预填可写账号 scanner / scan123456。</p>
      <section>
        <label>用户名</label><input v-model="loginUser" autocomplete="off" />
        <label>密码</label><input type="password" v-model="loginPass" autocomplete="off" />
        <button :disabled="loading" @click="login">登录</button>
        <p v-if="error" class="err">{{ error }}</p>
      </section>
    </div>
    <div v-else>
      <nav class="topbar">
        <button class="tab" :class="{ on: view === 'scans' }" @click="view = 'scans'">扫描台</button>
        <button class="tab" :class="{ on: view === 'handover' }" @click="openHandover">交班本</button>
        <span class="who">已登录：{{ session.username }}（{{ isWriter ? "可提交" : "只读" }}）</span>
        <button class="secondary" @click="logout">退出</button>
      </nav>
      <template v-if="view === 'scans'">
        <section>
          <button class="secondary" @click="refresh">刷新列表</button>
        </section>
        <section v-if="isWriter">
          <label>组串编号</label><input v-model="stringCode" placeholder="例如 阵列C-串05" />
          <label>开路电压 V</label><input type="number" step="0.1" v-model="voc" />
          <label>短路电流 A</label><input type="number" step="0.1" v-model="isc" />
          <label>填充因子</label><input type="number" step="0.01" v-model="ff" />
          <button :disabled="loading" @click="submit">提交扫描</button>
          <p v-if="error" class="err">{{ error }}</p>
        </section>
        <section>
          <table>
            <thead>
              <tr><th>编号</th><th>组串</th><th>Voc</th><th>Isc</th><th>FF</th><th>状态</th><th>结论</th></tr>
            </thead>
            <tbody>
              <tr v-for="row in logs" :key="row.id">
                <td>{{ row.id }}</td>
                <td>{{ row.string_code }}</td>
                <td>{{ row.voc_v }}</td>
                <td>{{ row.isc_a }}</td>
                <td>{{ row.fill_factor }}</td>
                <td><span class="tag" :class="row.status === 'pending' ? 'pending' : 'ok'">{{ row.status === 'pending' ? '待处理' : '已完成' }}</span></td>
                <td><span v-if="row.verdict" class="tag" :class="row.verdict === '合格' ? 'ok' : 'bad'">{{ row.verdict }}</span><span v-else>—</span></td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>
      <template v-else>
        <section>
          <h2>盖章钮</h2>
          <template v-if="isWriter">
            <button :disabled="stamping" @click="stamp">{{ stamping ? "盖章中…" : "盖上三张计数章" }}</button>
            <p class="hint">按下这一瞬取当前总单数、合格数、衰减数写进新本正文并落库；盖上以后在线单据再变，也刮不掉本上的字。</p>
          </template>
          <p v-else class="hint">观察员只许翻已盖的本，不许再盖。</p>
          <p v-if="stampError" class="err">{{ stampError }}</p>
        </section>
        <section>
          <h2>旧本目录</h2>
          <p v-if="!books.length" class="hint">还没有盖过任何一本。</p>
          <ul v-else class="booklist">
            <li v-for="b in books" :key="b.id">
              <button class="book" :class="{ on: selected && selected.id === b.id }" @click="selected = b">
                第{{ b.id }}本 · {{ b.stamped_by }} 盖于 {{ fmtTime(b.stamped_at) }}
              </button>
            </li>
          </ul>
        </section>
        <section>
          <h2>正文预览</h2>
          <div v-if="selected">
            <p class="hint">第{{ selected.id }}本 · {{ selected.stamped_by }} 盖于 {{ fmtTime(selected.stamped_at) }}，计数停在盖章当时。</p>
            <div class="stamps">
              <div class="seal"><b>{{ selected.total_count }}</b><span>总单数</span></div>
              <div class="seal"><b>{{ selected.pass_count }}</b><span>合格</span></div>
              <div class="seal"><b>{{ selected.degraded_count }}</b><span>衰减</span></div>
            </div>
          </div>
          <p v-else class="empty">本子还是空的</p>
        </section>
      </template>
    </div>
  </main>
</template>
<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
const session = ref(null);
const logs = ref([]);
const loginUser = ref("scanner");
const loginPass = ref("scan123456");
const stringCode = ref("");
const voc = ref("");
const isc = ref("");
const ff = ref("");
const error = ref("");
const loading = ref(false);
const view = ref("scans");
const books = ref([]);
const selected = ref(null);
const stamping = ref(false);
const stampError = ref("");
let timer;
const isWriter = computed(() => session.value?.role === "writer");
function headers() {
  return session.value ? { Authorization: "Bearer " + session.value.token } : {};
}
async function refresh() {
  if (!session.value) return;
  const res = await fetch("/api/logs", { headers: headers() });
  if (res.status === 401) { logout(); return; }
  if (res.ok) logs.value = await res.json();
  if (view.value === "handover") await loadBooks();
}
async function loadBooks() {
  if (!session.value) return;
  const res = await fetch("/api/handover-books", { headers: headers() });
  if (res.status === 401) { logout(); return; }
  if (!res.ok) return;
  books.value = await res.json();
  if (selected.value) {
    selected.value = books.value.find((b) => b.id === selected.value.id) || null;
  }
}
function openHandover() {
  view.value = "handover";
  stampError.value = "";
  loadBooks();
}
async function stamp() {
  stampError.value = "";
  stamping.value = true;
  try {
    const res = await fetch("/api/handover-books", { method: "POST", headers: headers() });
    const data = await res.json();
    if (!res.ok) { stampError.value = data.detail || "盖章失败"; return; }
    await loadBooks();
    selected.value = books.value.find((b) => b.id === data.id) || data;
  } catch { stampError.value = "盖章时网络异常"; }
  finally { stamping.value = false; }
}
function fmtTime(iso) {
  return new Date(iso).toLocaleString("zh-CN", { hour12: false });
}
async function login() {
  error.value = "";
  loading.value = true;
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: loginUser.value, password: loginPass.value }),
    });
    const data = await res.json();
    if (!res.ok) { error.value = data.detail || "登录失败"; return; }
    session.value = { token: data.access_token, username: data.username, role: data.role };
    localStorage.setItem("pv_session", JSON.stringify(session.value));
    await refresh();
    timer = setInterval(refresh, 2000);
  } catch { error.value = "无法连接接口"; }
  finally { loading.value = false; }
}
function logout() {
  if (timer) clearInterval(timer);
  session.value = null;
  logs.value = [];
  view.value = "scans";
  books.value = [];
  selected.value = null;
  localStorage.removeItem("pv_session");
}
async function submit() {
  error.value = "";
  loading.value = true;
  try {
    const res = await fetch("/api/logs", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers() },
      body: JSON.stringify({
        string_code: stringCode.value,
        voc_v: Number(voc.value),
        isc_a: Number(isc.value),
        fill_factor: Number(ff.value),
      }),
    });
    const data = await res.json();
    if (!res.ok) { error.value = data.detail || "提交失败"; return; }
    stringCode.value = voc.value = isc.value = ff.value = "";
    await refresh();
  } catch { error.value = "提交时网络异常"; }
  finally { loading.value = false; }
}
onMounted(() => {
  const raw = localStorage.getItem("pv_session");
  if (raw) {
    try {
      session.value = JSON.parse(raw);
      refresh();
      timer = setInterval(refresh, 2000);
    } catch { localStorage.removeItem("pv_session"); }
  }
});
onUnmounted(() => { if (timer) clearInterval(timer); });
</script>
<style>
body { margin: 0; font-family: "Segoe UI", system-ui, sans-serif; background: #052e16; color: #ecfdf5; }
main { max-width: 980px; margin: 0 auto; padding: 1.5rem; }
h1 { color: #86efac; margin: 0 0 0.25rem; }
h2 { color: #86efac; font-size: 1rem; margin: 0 0 0.6rem; }
.sub { color: #a7f3d0; margin-bottom: 1.25rem; }
.topbar { display: flex; align-items: center; gap: 0.4rem; background: #14532d; border: 1px solid #166534; border-radius: 8px; padding: 0.6rem 0.8rem; margin-bottom: 1rem; }
.tab { background: #365314; }
.tab.on { background: #16a34a; }
.who { margin-left: auto; color: #a7f3d0; font-size: 0.85rem; }
section { background: #14532d; border: 1px solid #166534; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 1rem; }
label { display: block; font-size: 0.85rem; margin-bottom: 0.25rem; }
input { width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px; border: 1px solid #4ade80; background: #022c22; color: #ecfdf5; margin-bottom: 0.75rem; }
button { cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px; background: #16a34a; color: #fff; font-weight: 600; margin-right: 0.4rem; }
button.secondary { background: #365314; }
.err { color: #fecaca; }
.hint { color: #a7f3d0; font-size: 0.85rem; margin: 0.5rem 0 0; }
.empty { color: #a7f3d0; font-style: italic; }
.booklist { list-style: none; margin: 0; padding: 0; }
.booklist li { margin-bottom: 0.4rem; }
.book { width: 100%; text-align: left; background: #022c22; border: 1px solid #166534; font-weight: 400; }
.book.on { border-color: #4ade80; background: #14532d; font-weight: 600; }
.stamps { display: flex; gap: 1.25rem; margin-top: 0.75rem; }
.seal { width: 96px; height: 96px; border: 3px solid #f87171; border-radius: 50%; color: #fecaca; display: flex; flex-direction: column; align-items: center; justify-content: center; transform: rotate(-8deg); }
.seal b { font-size: 1.6rem; line-height: 1; }
.seal span { font-size: 0.8rem; margin-top: 0.3rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #166534; }
.tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
.ok { background: #14532d; color: #bbf7d0; }
.bad { background: #7f1d1d; color: #fecaca; }
.pending { background: #854d0e; color: #fde68a; }
</style>
