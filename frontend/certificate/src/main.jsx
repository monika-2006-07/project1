import React from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import CertificatePreview from "./CertificatePreview.jsx";

const payload = window.__CERTIFICATE_DATA__;
const el = document.getElementById("certificate-root");

if (el && payload) {
  createRoot(el).render(
    <React.StrictMode>
      <CertificatePreview initialData={payload} />
    </React.StrictMode>
  );
}
