import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";
import "../styles/family.css";

const root = document.getElementById("root");
if (!root) throw new Error("PolicyLens root element is missing");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>
);
