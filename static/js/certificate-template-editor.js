/**
 * Admin: drag/resize boxes on certificate template to mark where each field is replaced.
 */
(function () {
  const editor = document.getElementById("cert-template-editor");
  if (!editor) return;

  const img = document.getElementById("cert-template-img");
  const layer = document.getElementById("cert-field-layer");
  const hidden = document.getElementById("certificate_field_regions");
  if (!img || !layer || !hidden) return;

  let config = {};
  try {
    config = JSON.parse(hidden.value || "{}");
  } catch (e) {
    config = {};
  }
  if (config.fields) config = config.fields;

  const FIELD_LABELS = {
    studentName: "Student name",
    courseName: "Course",
    completionDate: "Date",
    instructorName: "Instructor",
    founderName: "Founder / Director",
    certificateId: "Cert ID",
  };

  let activeBox = null;
  let drag = null;

  function saveConfig() {
    const fields = {};
    layer.querySelectorAll(".cert-field-box").forEach((box) => {
      const key = box.dataset.field;
      const r = box.getBoundingClientRect();
      const lr = layer.getBoundingClientRect();
      const w = lr.width || 1;
      const h = lr.height || 1;
      const cx = ((r.left + r.width / 2) - lr.left) / w * 100;
      const cy = ((r.top + r.height / 2) - lr.top) / h * 100;
      const width = (r.width / w) * 100;
      const height = (r.height / h) * 100;
      fields[key] = {
        top: Math.round(cy * 10) / 10,
        left: Math.round(cx * 10) / 10,
        width: Math.round(width * 10) / 10,
        height: Math.round(height * 10) / 10,
      };
      if (config[key]) {
        Object.assign(fields[key], {
          placeholder: config[key].placeholder,
          fontSizePercent: config[key].fontSizePercent,
          align: config[key].align,
          color: config[key].color,
          label: config[key].label,
        });
      }
    });
    hidden.value = JSON.stringify(fields);
  }

  function createBox(key, cfg) {
    const box = document.createElement("div");
    box.className = "cert-field-box";
    box.dataset.field = key;
    const top = cfg.top != null ? cfg.top : 50;
    const left = cfg.left != null ? cfg.left : 50;
    const width = cfg.width != null ? cfg.width : 25;
    const height = cfg.height != null ? cfg.height : 5;
    box.style.cssText = [
      "position:absolute",
      `left:${left - width / 2}%`,
      `top:${top - height / 2}%`,
      `width:${width}%`,
      `height:${height}%`,
      "border:2px dashed #2563eb",
      "background:rgba(37,99,235,0.12)",
      "cursor:move",
      "box-sizing:border-box",
      "border-radius:4px",
      "z-index:5",
    ].join(";");
    const label = document.createElement("span");
    label.textContent = FIELD_LABELS[key] || key;
    label.style.cssText =
      "position:absolute;top:2px;left:4px;font-size:10px;font-weight:700;color:#1e40af;background:rgba(255,255,255,0.85);padding:1px 4px;border-radius:3px;pointer-events:none;";
    box.appendChild(label);
    layer.appendChild(box);

    box.addEventListener("mousedown", (e) => {
      if (e.target !== box && !box.contains(e.target)) return;
      activeBox = box;
      const rect = box.getBoundingClientRect();
      const lr = layer.getBoundingClientRect();
      drag = {
        box,
        startX: e.clientX,
        startY: e.clientY,
        startLeft: parseFloat(box.style.left),
        startTop: parseFloat(box.style.top),
        layerW: lr.width,
        layerH: lr.height,
      };
      e.preventDefault();
    });
  }

  document.addEventListener("mousemove", (e) => {
    if (!drag) return;
    const dx = ((e.clientX - drag.startX) / drag.layerW) * 100;
    const dy = ((e.clientY - drag.startY) / drag.layerH) * 100;
    drag.box.style.left = `${drag.startLeft + dx}%`;
    drag.box.style.top = `${drag.startTop + dy}%`;
  });

  document.addEventListener("mouseup", () => {
    if (drag) {
      saveConfig();
      drag = null;
    }
  });

  function initBoxes() {
    layer.innerHTML = "";
    Object.keys(FIELD_LABELS).forEach((key) => {
      const cfg = config[key] || { top: 50, left: 50, width: 20, height: 5 };
      createBox(key, cfg);
    });
    saveConfig();
  }

  if (img.complete) initBoxes();
  else img.addEventListener("load", initBoxes);

  const form = editor.closest("form");
  if (form) {
    form.addEventListener("submit", saveConfig);
  }
})();
