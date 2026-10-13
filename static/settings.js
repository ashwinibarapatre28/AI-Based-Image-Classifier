document.addEventListener("DOMContentLoaded", function () {
    /* =====================================================
       TOAST NOTIFICATION HELPER
    ====================================================== */
    const toast = document.getElementById("toastMessage");

    function showToast(message, type = "success") {
        if (!toast) return;
        toast.textContent = message;
        toast.className = `toast-notification toast-${type}`;
        toast.style.display = "block";

        setTimeout(() => {
            toast.style.display = "none";
        }, 3500);
    }

    /* =====================================================
       1. THEME SWITCHER
    ====================================================== */
    const currentTheme = localStorage.getItem("ai_vision_theme") || "light";
    const themeRadios = document.querySelectorAll('input[name="app_theme"]');

    themeRadios.forEach((radio) => {
        if (radio.value === currentTheme) {
            radio.checked = true;
        }

        radio.addEventListener("change", function () {
            const selected = this.value;
            localStorage.setItem("ai_vision_theme", selected);

            if (selected === "light") {
                document.documentElement.removeAttribute("data-theme");
            } else {
                document.documentElement.setAttribute("data-theme", selected);
            }

            const names = {
                light: "Light Minimal",
                dark: "Dark Eclipse"
            };
            showToast(`Theme changed to ${names[selected] || selected}!`);
        });
    });

    /* =====================================================
       2. AI MODEL & CONFIDENCE PREFERENCES
    ====================================================== */
    const defaultModel = localStorage.getItem("ai_vision_default_model") || "yolo";
    const modelRadios = document.querySelectorAll('input[name="default_model"]');

    modelRadios.forEach((radio) => {
        if (radio.value === defaultModel) {
            radio.checked = true;
        }
        radio.addEventListener("change", function () {
            localStorage.setItem("ai_vision_default_model", this.value);
            const label = this.value === "faster_rcnn" ? "Faster R-CNN" : "YOLOv8";
            showToast(`Default AI model set to ${label}.`);
        });
    });

    const confidenceSlider = document.getElementById("confidenceSlider");
    const confidenceBadge = document.getElementById("confidenceValueBadge");
    const savedConfidence = localStorage.getItem("ai_vision_confidence") || "50";

    if (confidenceSlider && confidenceBadge) {
        confidenceSlider.value = savedConfidence;
        confidenceBadge.textContent = savedConfidence + "%";

        confidenceSlider.addEventListener("input", function () {
            confidenceBadge.textContent = this.value + "%";
        });

        confidenceSlider.addEventListener("change", function () {
            localStorage.setItem("ai_vision_confidence", this.value);
            showToast(`Default confidence threshold set to ${this.value}%.`);
        });
    }

    /* =====================================================
       3. PDF EXPORT (jsPDF + autoTable)
    ====================================================== */
    const exportPdfBtn = document.getElementById("exportPdfBtn");

    if (exportPdfBtn) {
        exportPdfBtn.addEventListener("click", async function () {
            exportPdfBtn.disabled = true;
            const originalHtml = exportPdfBtn.innerHTML;
            exportPdfBtn.innerHTML = `
                <span class="export-icon">⏳</span>
                <div class="export-btn-text">
                    <strong>Generating PDF...</strong>
                    <span>Fetching detection records</span>
                </div>
            `;

            try {
                const response = await fetch("/api/history/data");
                const resData = await response.json();

                if (!resData.success || !resData.records || resData.records.length === 0) {
                    showToast("No detection records found to export.", "error");
                    exportPdfBtn.disabled = false;
                    exportPdfBtn.innerHTML = originalHtml;
                    return;
                }

                const records = resData.records;

                // Check jsPDF availability
                if (window.jspdf && window.jspdf.jsPDF) {
                    const { jsPDF } = window.jspdf;
                    const doc = new jsPDF("p", "pt", "a4");

                    // Document Header
                    doc.setFillColor(37, 99, 235);
                    doc.rect(0, 0, 595.28, 70, "F");

                    doc.setTextColor(255, 255, 255);
                    doc.setFontSize(20);
                    doc.setFont("helvetica", "bold");
                    doc.text("AI Vision Analyzer", 40, 38);

                    doc.setFontSize(10);
                    doc.setFont("helvetica", "normal");
                    doc.text("Object Detection & Image Analysis Report", 40, 54);

                    // Report Meta Info
                    doc.setTextColor(70, 70, 70);
                    doc.setFontSize(10);
                    const now = new Date().toLocaleString();
                    doc.text(`Generated on: ${now}`, 40, 95);
                    doc.text(`Total Detections Logged: ${records.length}`, 40, 110);

                    // Prepare table data
                    const tableRows = records.map((r, index) => [
                        index + 1,
                        r.image_name || "N/A",
                        r.object_name || "N/A",
                        (r.model_name || "YOLOv8"),
                        `${r.confidence}%`,
                        r.created_at || "N/A"
                    ]);

                    doc.autoTable({
                        head: [["#", "Image Name", "Detected Object", "Model", "Confidence", "Date & Time"]],
                        body: tableRows,
                        startY: 125,
                        theme: "striped",
                        headStyles: {
                            fillColor: [37, 99, 235],
                            textColor: [255, 255, 255],
                            fontStyle: "bold",
                            fontSize: 9
                        },
                        bodyStyles: {
                            fontSize: 8,
                            textColor: [40, 40, 40]
                        },
                        alternateRowStyles: {
                            fillColor: [245, 248, 255]
                        },
                        columnStyles: {
                            0: { cellWidth: 25 },
                            1: { cellWidth: 150 },
                            2: { cellWidth: 100 },
                            3: { cellWidth: 80 },
                            4: { cellWidth: 65 },
                            5: { cellWidth: 100 }
                        },
                        margin: { left: 40, right: 40 }
                    });

                    // Save PDF file
                    const dateStr = new Date().toISOString().slice(0, 10);
                    doc.save(`AI_Vision_Report_${dateStr}.pdf`);
                    showToast("PDF report downloaded successfully!");
                } else {
                    // Fallback to print report
                    window.open("/history", "_blank");
                    showToast("Opening history view for PDF printing.");
                }
            } catch (err) {
                console.error("PDF export error:", err);
                showToast("Failed to generate PDF report.", "error");
            } finally {
                exportPdfBtn.disabled = false;
                exportPdfBtn.innerHTML = originalHtml;
            }
        });
    }

    /* =====================================================
       4. DELETE HISTORY MODAL & ACTION
    ====================================================== */
    const openClearModalBtn = document.getElementById("openClearModalBtn");
    const clearModal = document.getElementById("clearModal");
    const closeModalBtn = document.getElementById("closeModalBtn");
    const cancelModalBtn = document.getElementById("cancelModalBtn");
    const confirmClearBtn = document.getElementById("confirmClearBtn");
    const deleteFilesCheckbox = document.getElementById("deleteFilesCheckbox");

    function openModal() {
        if (clearModal) clearModal.classList.remove("hidden");
    }

    function closeModal() {
        if (clearModal) clearModal.classList.add("hidden");
    }

    if (openClearModalBtn) openClearModalBtn.addEventListener("click", openModal);
    if (closeModalBtn) closeModalBtn.addEventListener("click", closeModal);
    if (cancelModalBtn) cancelModalBtn.addEventListener("click", closeModal);

    // Close on clicking outside modal box
    if (clearModal) {
        clearModal.addEventListener("click", function (e) {
            if (e.target === clearModal) closeModal();
        });
    }

    if (confirmClearBtn) {
        confirmClearBtn.addEventListener("click", async function () {
            confirmClearBtn.disabled = true;
            confirmClearBtn.textContent = "Deleting...";

            try {
                const response = await fetch("/api/history/clear", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        delete_files: deleteFilesCheckbox ? deleteFilesCheckbox.checked : false
                    })
                });

                const data = await response.json();

                if (data.success) {
                    // Update UI counters
                    const exportRecordCount = document.getElementById("exportRecordCount");
                    const statTotalDetections = document.getElementById("statTotalDetections");
                    const statUploadsCount = document.getElementById("statUploadsCount");

                    if (exportRecordCount) exportRecordCount.textContent = "0 detections";
                    if (statTotalDetections) statTotalDetections.textContent = "0";
                    if (deleteFilesCheckbox && deleteFilesCheckbox.checked && statUploadsCount) {
                        statUploadsCount.textContent = "0 files";
                    }

                    closeModal();
                    showToast(data.message || "Detection history has been deleted.");
                } else {
                    showToast(data.message || "Failed to clear history.", "error");
                }
            } catch (err) {
                console.error("Error clearing history:", err);
                showToast("Server error while clearing history.", "error");
            } finally {
                confirmClearBtn.disabled = false;
                confirmClearBtn.textContent = "Yes, Delete All History";
            }
        });
    }
});
