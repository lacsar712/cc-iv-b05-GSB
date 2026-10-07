<template>
  <main>
    <h1>光伏组串IV扫描台</h1>
    <template v-if="!session">
      <p class="sub">扫描员提交开路电压、短路电流与填充因子；通知通道叫醒工人出结论。登录框已预填可写账号 scanner / scan123456。</p>
      <section>
        <label>用户名</label><input v-model="loginUser" autocomplete="off" />
        <label>密码</label><input type="password" v-model="loginPass" autocomplete="off" />
        <button :disabled="loading" @click="login">登录</button>
        <p v-if="error" class="err">{{ error }}</p>
      </section>
    </template>
    <template v-else>
      <nav class="topbar">
        <button class="nav" :class="{ active: view === 'scan' }" @click="view = 'scan'">扫描台</button>
        <button class="nav" :class="{ active: view === 'book' }" @click="openBookPage">交班本</button>
        <span class="who">已登录：{{ session.username }}（{{ isWriter ? "可提交" : "只读" }}）</span>
        <button class="secondary" @click="logout">退出</button>
      </nav>

      <div v-if="view === 'scan'">
        <p class="sub">已登录：{{ session.username }}（{{ isWriter ? "可提交" : "只读" }}）</p>
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
      </div>

      <div v-else>
        <p class="sub">运维离岗前把当时三张计数章盖进交班本；本上的字落库即定型，在线单据再变也刮不掉。</p>

        <section class="stamp">
          <template v-if="isWriter">
            <button :disabled="stamping" @click="stamp">盖章</button>
            <span class="hint">按下瞬间取数：在线单据总数 / 合格 / 衰减。一张单都没有时也能盖出全零。</span>
          </template>
          <p v-else class="hint">观察员只许翻看已盖的本，不许再盖。</p>
          <p v-if="bookError" class="err">{{ bookError }}</p>
        </section>

        <section>
          <div class="section-head">
            <h2>旧本目录</h2>
            <button class="secondary small" @click="loadBooks">刷新目录</button>
          </div>
          <table v-if="books.length">
            <thead>
              <tr><th>本号</th><th>盖章时间</th><th>交班人</th><th>总数</th><th>合格</th><th>衰减</th><th></th></tr>
            </thead>
            <tbody>
              <tr v-for="b in books" :key="b.id" :class="{ chosen: selectedId === b.id }">
                <td>{{ b.id }}</td>
                <td>{{ fmtTime(b.stamped_at) }}</td>
                <td>{{ b.stamped_by }}</td>
                <td>{{ b.total_count }}</td>
                <td class="pass-n">{{ b.pass_count }}</td>
                <td class="decay-n">{{ b.decay_count }}</td>
                <td><button class="secondary small" @click="openBook(b.id)">翻看</button></td>
              </tr>
            </tbody>
          </table>
          <p v-else class="empty">本子还是空的。</p>
        </section>

        <section>
          <h2>正文预览</h2>
          <pre v-if="current" class="body">{{ current.body }}</pre>
          <p v-else class="empty">尚未翻看任何旧本。</p>
        </section>
      </div>
    </template>
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
const view = ref("scan");
const books = ref([]);
const current = ref(null);
const selectedId = ref(null);
const stamping = ref(false);
const bookError = ref("");
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
  books.value = [];
  current.value = null;
  selectedId.value = null;
  view.value = "scan";
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
async function loadBooks() {
  if (!session.value) return;
  const res = await fetch("/api/handover-books", { headers: headers() });
  if (res.status === 401) { logout(); return; }
  if (res.ok) books.value = await res.json();
}
async function openBook(id) {
  bookError.value = "";
  const res = await fetch(`/api/handover-books/${id}`, { headers: headers() });
  if (res.status === 401) { logout(); return; }
  const data = await res.json();
  if (!res.ok) { bookError.value = data.detail || "打不开这本旧本"; return; }
  current.value = data;
  selectedId.value = id;
}
async function openBookPage() {
  view.value = "book";
  bookError.value = "";
  await loadBooks();
}
async function stamp() {
  bookError.value = "";
  stamping.value = true;
  try {
    const res = await fetch("/api/handover-books", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers() },
    });
    const data = await res.json();
    if (!res.ok) { bookError.value = data.detail || "盖章失败"; return; }
    await loadBooks();
    // 预览只认盖章时落库返回的内容；之后在线单据变化不再改它
    current.value = data;
    selectedId.value = data.id;
  } catch { bookError.value = "盖章时网络异常"; }
  finally { stamping.value = false; }
}
function fmtTime(iso) {
  if (!iso) return "";
  return iso.replace("T", " ").replace(/\.\d+.*$/, " UTC");
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
h2 { font-size: 1rem; color: #86efac; margin: 0 0 0.5rem; }
.sub { color: #a7f3d0; margin-bottom: 1.25rem; }
.topbar { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1.25rem; }
.topbar .who { margin-left: auto; color: #a7f3d0; font-size: 0.9rem; }
.nav { background: transparent; border: 1px solid #166534; color: #a7f3d0; }
.nav.active { background: #14532d; border-color: #4ade80; color: #ecfdf5; }
section { background: #14532d; border: 1px solid #166534; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 1rem; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem; }
.stamp .hint { color: #a7f3d0; font-size: 0.85rem; margin-left: 0.5rem; }
label { display: block; font-size: 0.85rem; margin-bottom: 0.25rem; }
input { width: 100%; box-sizing: border-box; padding: 0.5rem 0.65rem; border-radius: 6px; border: 1px solid #4ade80; background: #022c22; color: #ecfdf5; margin-bottom: 0.75rem; }
button { cursor: pointer; padding: 0.5rem 1rem; border: none; border-radius: 6px; background: #16a34a; color: #fff; font-weight: 600; margin-right: 0.4rem; }
button.secondary { background: #365314; }
button.small { padding: 0.25rem 0.6rem; font-size: 0.8rem; margin: 0; }
.err { color: #fecaca; }
.empty { color: #a7f3d0; font-style: italic; }
.body { white-space: pre-wrap; word-break: break-word; margin: 0; font-family: ui-monospace, "Cascadia Code", Consolas, monospace; font-size: 0.88rem; line-height: 1.55; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th, td { text-align: left; padding: 0.45rem; border-bottom: 1px solid #166534; }
tr.chosen { background: #166534; }
.pass-n { color: #bbf7d0; }
.decay-n { color: #fecaca; }
.tag { padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.8rem; }
.ok { background: #14532d; color: #bbf7d0; }
.bad { background: #7f1d1d; color: #fecaca; }
.pending { background: #854d0e; color: #fde68a; }
</style>
