const uploadForm =
    document.getElementById("uploadForm");

const imageInput =
    document.getElementById("imageInput");

const resultSection =
    document.getElementById("resultSection");

const resultImage =
    document.getElementById("resultImage");

const totalObjects =
    document.getElementById("totalObjects");

const detectedObjects =
    document.getElementById("detectedObjects");

const statusMessage =
    document.getElementById("statusMessage");

const analyzeButton =
    document.querySelector(".analyze-btn");


/* =====================================================
   ANALYZE IMAGE
===================================================== */

uploadForm.addEventListener(
    "submit",
    async function(event) {

        event.preventDefault();


        const file =
            imageInput.files[0];


        /* =============================================
           CHECK FILE
        ============================================== */

        if (!file) {

            statusMessage.textContent =
                "Please choose an image first.";

            return;
        }


        /* =============================================
           DISABLE BUTTON
        ============================================== */

        analyzeButton.disabled = true;

        analyzeButton.textContent =
            "Analyzing...";


        statusMessage.textContent =
            "AI is analyzing the image...";


        /* =============================================
           CREATE FORM DATA
        ============================================== */

        const formData =
            new FormData();

        formData.append(
            "image",
            file
        );


        try {


            /* =========================================
               SEND IMAGE TO FLASK
            ========================================== */

            const response =
                await fetch(
                    "/detect",
                    {
                        method: "POST",
                        body: formData
                    }
                );


            const data =
                await response.json();


            /* =========================================
               CHECK RESPONSE
            ========================================== */

            if (!data.success) {

                statusMessage.textContent =
                    data.message ||
                    "Analysis failed.";

                return;
            }


            /* =========================================
               RESULT IMAGE
            ========================================== */

            resultImage.src =
                data.image +
                "?t=" +
                new Date().getTime();


            /* =========================================
               TOTAL OBJECTS
            ========================================== */

            totalObjects.textContent =
                data.total_objects;


            /* =========================================
               REMOVE OLD OBJECT RESULTS
            ========================================== */

            detectedObjects.innerHTML = "";


            /* =========================================
               DISPLAY EACH DETECTED OBJECT
            ========================================== */

            data.detections.forEach(
                function(detection) {


                    const objectItem =
                        document.createElement(
                            "div"
                        );


                    objectItem.className =
                        "object-item";


                    const objectName =
                        document.createElement(
                            "span"
                        );


                    objectName.textContent =
                        detection.class;


                    const confidence =
                        document.createElement(
                            "strong"
                        );


                    confidence.textContent =
                        detection.confidence +
                        "%";


                    objectItem.appendChild(
                        objectName
                    );


                    objectItem.appendChild(
                        confidence
                    );


                    detectedObjects.appendChild(
                        objectItem
                    );

                }
            );


            /* =========================================
               SHOW RESULT
            ========================================== */

            resultSection.classList.remove(
                "hidden"
            );


            statusMessage.textContent =
                "Analysis completed successfully.";


            /* =========================================
               SCROLL TO RESULT
            ========================================== */

            resultSection.scrollIntoView({
                behavior: "smooth",
                block: "start"
            });


            /* =========================================
               DO NOT RELOAD PAGE
               
               IMPORTANT:
               We intentionally DON'T use:
               
               location.reload();
               
               because the result is being displayed
               dynamically on the Dashboard.
            ========================================== */


        }

        catch (error) {

            console.error(
                "Detection Error:",
                error
            );


            statusMessage.textContent =
                "Something went wrong while analyzing the image.";

        }


        finally {

            analyzeButton.disabled =
                false;

            analyzeButton.textContent =
                "Analyze Image";

        }

    }
);