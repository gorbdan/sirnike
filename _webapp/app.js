const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

const categoriesEl = document.getElementById("categories");
const cardsEl = document.getElementById("cards");
const emptyEl = document.getElementById("empty");

let library = [];
let activeCategory = 0;

async function loadLibrary() {
  try {
    const res = await fetch("./prompt_library.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!Array.isArray(data)) throw new Error("Invalid format");
    library = data;
  } catch (e) {
    console.error("Failed to load prompt library", e);
    library = [];
  }
}

function renderCategories() {
  categoriesEl.innerHTML = "";
  library.forEach((cat, idx) => {
    const btn = document.createElement("button");
    btn.className = `chip ${idx === activeCategory ? "active" : ""}`;
    btn.textContent = `${cat.emoji || "📁"} ${cat.title || "Категория"}`;
    btn.onclick = () => {
      activeCategory = idx;
      renderCategories();
      renderCards();
    };
    categoriesEl.appendChild(btn);
  });
}

function sendPrompt(item, button) {
  const fallbackPrompt = (item.title || "").trim();
  const payload = {
    action: "set_prompt",
    title: item.title || "Шаблон",
    prompt: (item.prompt || "").trim() || fallbackPrompt,
    example_url: item.example_url || "",
  };

  if (!tg) {
    alert("Открой этот экран внутри Telegram, чтобы отправить шаблон в бота.");
    return;
  }

  try {
    tg.sendData(JSON.stringify(payload));
    if (button) {
      button.disabled = true;
      button.textContent = "Применено ✅";
    }
    setTimeout(() => tg.close(), 900);
  } catch (e) {
    console.error("sendData failed", e);
    alert("Не получилось применить шаблон. Попробуй еще раз.");
  }
}

function renderCards() {
  cardsEl.innerHTML = "";
  emptyEl.classList.add("hidden");

  const category = library[activeCategory];
  const items = Array.isArray(category?.items) ? category.items : [];
  if (!items.length) {
    emptyEl.classList.remove("hidden");
    return;
  }

  for (const item of items) {
    const card = document.createElement("article");
    card.className = "card";

    const image = document.createElement("img");
    image.className = "preview";
    image.loading = "lazy";
    image.alt = item.title || "Пример";
    image.src = item.example_url || "https://dummyimage.com/960x640/e2e8f0/64748b&text=No+Preview";

    const content = document.createElement("div");
    content.className = "content";

    const title = document.createElement("h3");
    title.className = "title";
    title.textContent = item.title || "Без названия";

    const useBtn = document.createElement("button");
    useBtn.className = "btn";
    useBtn.textContent = "Использовать";
    useBtn.onclick = () => sendPrompt(item, useBtn);

    content.appendChild(title);
    content.appendChild(useBtn);

    card.appendChild(image);
    card.appendChild(content);
    cardsEl.appendChild(card);
  }
}

(async function init() {
  await loadLibrary();
  if (!library.length) {
    emptyEl.classList.remove("hidden");
    emptyEl.textContent = "Не удалось загрузить библиотеку. Проверь prompt_library.json.";
    return;
  }
  renderCategories();
  renderCards();
})();
