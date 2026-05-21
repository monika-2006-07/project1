import { useState, useRef, useCallback, useEffect } from "react";
import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";

const FIELD_ORDER = [
  "studentName",
  "courseName",
  "completionDate",
  "certificateId",
  "instructorName",
];

function fieldStyle(field) {
  return {
    position: "absolute",
    top: field.top != null ? `${field.top}%` : undefined,
    left: field.left != null ? `${field.left}%` : undefined,
    fontSize: field.fontSize,
    fontFamily: field.fontFamily,
    fontWeight: field.fontWeight,
    color: field.color,
    textAlign: field.textAlign || "center",
    transform: field.transform || "translateX(-50%)",
    maxWidth: field.maxWidth,
    margin: 0,
    padding: 0,
    lineHeight: field.lineHeight || 1.35,
    whiteSpace: field.whiteSpace || "normal",
    zIndex: 2,
  };
}

function fieldText(data, key) {
  const map = {
    studentName: data.studentName,
    courseName: data.courseName,
    completionDate: data.completionDate,
    certificateId: data.certificateCode,
    instructorName: data.instructorName,
  };
  return map[key] || "";
}

function CertificateCanvas({ data, innerRef }) {
  const ratio = data.aspectRatio || 1.414;
  return (
    <div
      ref={innerRef}
      className="relative w-full bg-white overflow-hidden shadow-2xl"
      style={{ aspectRatio: String(ratio) }}
    >
      <img
        src={data.templateUrl}
        alt="Certificate template"
        crossOrigin="anonymous"
        className="absolute inset-0 w-full h-full object-cover pointer-events-none select-none"
        draggable={false}
      />
      {FIELD_ORDER.map((key) => {
        const cfg = data.fields?.[key];
        if (!cfg) return null;
        const text = fieldText(data, key);
        if (!text) return null;
        return (
          <p key={key} className="certificate-field" style={fieldStyle(cfg)}>
            {text}
          </p>
        );
      })}
    </div>
  );
}

export default function CertificatePreview({ initialData }) {
  const [data] = useState(initialData);
  const [downloading, setDownloading] = useState(false);
  const [imgReady, setImgReady] = useState(false);
  const certRef = useRef(null);

  useEffect(() => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => setImgReady(true);
    img.onerror = () => setImgReady(true);
    img.src = data.templateUrl;
  }, [data.templateUrl]);

  const downloadPdf = useCallback(async () => {
    if (!certRef.current) return;
    setDownloading(true);
    try {
      const canvas = await html2canvas(certRef.current, {
        scale: 3,
        useCORS: true,
        allowTaint: true,
        backgroundColor: "#ffffff",
        logging: false,
      });
      const imgData = canvas.toDataURL("image/jpeg", 0.98);
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

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center py-6 px-4 sm:py-10">
      <div className="no-print w-full max-w-5xl flex flex-wrap items-center justify-center gap-3 mb-6">
        <button
          type="button"
          onClick={downloadPdf}
          disabled={downloading || !imgReady}
          className="inline-flex items-center gap-2 rounded-full bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white font-semibold px-6 py-3 shadow-lg transition"
        >
          {downloading ? "Generating PDF…" : "Download PDF"}
        </button>
        <button
          type="button"
          onClick={() => window.print()}
          className="inline-flex items-center gap-2 rounded-full bg-slate-700 hover:bg-slate-600 text-white font-semibold px-6 py-3 shadow transition"
        >
          Print
        </button>
        <a
          href="/my_certificates"
          className="inline-flex items-center gap-2 rounded-full border border-slate-600 text-slate-300 hover:text-white font-medium px-5 py-3 transition"
        >
          ← My Certificates
        </a>
      </div>

      <div className="w-full max-w-[1000px] certificate-print-target">
        <CertificateCanvas data={data} innerRef={certRef} />
      </div>

      <p className="no-print mt-4 text-slate-500 text-xs font-mono">
        ID: {data.certificateCode}
      </p>
    </div>
  );
}
