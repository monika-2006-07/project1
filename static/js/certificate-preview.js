/**
 * Certificate preview — React overlay on uploaded template + PDF export (html2canvas + jsPDF)
 */
(function () {
  const { useState, useRef, useCallback, useEffect, createElement: h } = React;

  const FIELD_ORDER = [
    "studentName",
    "courseName",
    "completionDate",
    "certificateId",
    "instructorName",
  ];

  function fieldStyle(field) {
    const top = field.top != null ? field.top + "%" : undefined;
    const left = field.left != null ? field.left + "%" : undefined;
    return {
      position: "absolute",
      top,
      left,
      fontSize: field.fontSize,
      fontFamily: field.fontFamily,
      fontWeight: field.fontWeight,
      color: field.color,
      textAlign: field.textAlign || "center",
      transform: field.transform || "translateX(-50%)",
      maxWidth: field.maxWidth,
      margin: 0,
      padding: 0,
      lineHeight: field.lineHeight != null ? field.lineHeight : 1.35,
      whiteSpace: field.whiteSpace || "normal",
      letterSpacing: field.letterSpacing,
      textTransform: field.textTransform,
      zIndex: 2,
    };
  }

  function fieldText(data, key) {
    const map = {
      studentName: data.studentName,
      courseName: data.courseName,
      completionDate: data.completionDate,
      certificateId: data.certificateCode ? `ID: ${data.certificateCode}` : "",
      instructorName: data.instructorName,
    };
    return map[key] || "";
  }

  function isSameOriginUrl(url) {
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch (e) {
      return true;
    }
  }

  function CertificateCanvas({ data, innerRef }) {
    const ratio = data.aspectRatio || 1.414;
    const imgProps = {
      src: data.templateUrl,
      alt: "Certificate template",
      className: "absolute inset-0 w-full h-full object-cover pointer-events-none select-none",
      draggable: false,
      onError: (e) => {
        e.target.style.display = "none";
        console.error("Certificate template failed to load:", data.templateUrl);
      },
    };
    if (!isSameOriginUrl(data.templateUrl)) {
      imgProps.crossOrigin = "anonymous";
    }
    return h(
      "div",
      {
        ref: innerRef,
        className: "relative w-full bg-white overflow-hidden shadow-2xl",
        style: { aspectRatio: String(ratio) },
      },
      h("img", imgProps),
      FIELD_ORDER.map((key) => {
        const cfg = data.fields && data.fields[key];
        if (!cfg) return null;
        const text = fieldText(data, key);
        if (!text) return null;
        return h(
          "p",
          {
            key,
            className: "certificate-field",
            style: fieldStyle(cfg),
          },
          text
        );
      })
    );
  }

  function CertificatePreview({ initialData }) {
    const [data] = useState(initialData);
    const [downloading, setDownloading] = useState(false);
    const [imgReady, setImgReady] = useState(false);
    const certRef = useRef(null);
    const embedMode = window.__CERTIFICATE_EMBED__ === true || window.__CERTIFICATE_EMBED__ === "true";

    useEffect(() => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => setImgReady(true);
      img.onerror = () => setImgReady(true);
      img.src = data.templateUrl;
    }, [data.templateUrl]);

    const downloadPdf = useCallback(async () => {
      if (!certRef.current || !window.html2canvas || !window.jspdf) return;
      setDownloading(true);
      try {
        const canvas = await window.html2canvas(certRef.current, {
          scale: 3,
          useCORS: true,
          allowTaint: true,
          backgroundColor: "#ffffff",
          logging: false,
        });
        const imgData = canvas.toDataURL("image/jpeg", 0.98);
        const { jsPDF } = window.jspdf;
        const pdf = new jsPDF({
          orientation: canvas.width >= canvas.height ? "landscape" : "portrait",
          unit: "px",
          format: [canvas.width, canvas.height],
          compress: true,
        });
        pdf.addImage(imgData, "JPEG", 0, 0, canvas.width, canvas.height);
        pdf.save(`certificate-${data.certificateCode}.pdf`);
      } catch (err) {
        console.error(err);
        alert("Could not generate PDF. Please try again or use Print.");
      } finally {
        setDownloading(false);
      }
    }, [data.certificateCode]);

    useEffect(() => {
      if (new URLSearchParams(window.location.search).get("download") === "1" && imgReady) {
        downloadPdf();
      }
    }, [imgReady, downloadPdf]);

    if (embedMode) {
      return h(
        "div",
        { className: "w-full bg-white p-0" },
        h(CertificateCanvas, { data, innerRef: certRef })
      );
    }

    return h(
      "div",
      { className: "min-h-screen bg-slate-900 flex flex-col items-center py-6 px-4 sm:py-10" },
      h(
        "div",
        { className: "no-print w-full max-w-5xl flex flex-wrap items-center justify-center gap-3 mb-6" },
        h(
          "button",
          {
            type: "button",
            onClick: downloadPdf,
            disabled: downloading || !imgReady,
            className:
              "inline-flex items-center gap-2 rounded-full bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white font-semibold px-6 py-3 shadow-lg transition",
          },
          downloading ? "Generating PDF…" : "Download PDF"
        ),
        h(
          "button",
          {
            type: "button",
            onClick: () => window.print(),
            className:
              "inline-flex items-center gap-2 rounded-full bg-slate-700 hover:bg-slate-600 text-white font-semibold px-6 py-3 shadow transition",
          },
          "Print"
        ),
        h(
          "a",
          {
            href: "/my_certificates",
            className:
              "inline-flex items-center gap-2 rounded-full border border-slate-600 text-slate-300 hover:text-white font-medium px-5 py-3 transition",
          },
          "← My Certificates"
        )
      ),
      h(
        "div",
        { className: "w-full max-w-[1000px] certificate-print-target" },
        h(CertificateCanvas, { data, innerRef: certRef })
      ),
      h(
        "p",
        { className: "mt-4 text-slate-500 text-xs font-mono" },
        "ID: ",
        data.certificateCode
      )
    );
  }

  function mount() {
    const el = document.getElementById("certificate-root");
    const payload = window.__CERTIFICATE_DATA__;
    if (!el || !payload) return;
    const root = ReactDOM.createRoot(el);
    root.render(h(CertificatePreview, { initialData: payload }));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
