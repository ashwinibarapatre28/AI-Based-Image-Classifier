const imageInput = document.getElementById("imageInput");
const analyzeBtn = document.getElementById("analyzeBtn");

const statusText = document.getElementById("status");

const resultsSection = document.getElementById("results");

const resultImage = document.getElementById("resultImage");

const totalObjects = document.getElementById("totalObjects");

const detectionList = document.getElementById("detectionList");


analyzeBtn.addEventListener("click", async () => {

    const file = imageInput.files[0];

    if (!file) {
        statusText.textContent = "Please select an image first.";
        return;
    }

    const formData = new FormData();

    formData.append("image", file);

    statusText.textContent = "AI is analyzing the image...";

    analyzeBtn.disabled = true;


    try {

        const response = await fetch("/detect", {
            method: "POST",
            body: formData
        });

        const data = await response.json();


        if (!data.success) {

            statusText.textContent = data.message;

            return;
        }


        statusText.textContent =
            "Analysis completed successfully.";


        // Show result image
        resultImage.src =
            data.image + "?t=" + new Date().getTime();


        // Show total objects
        totalObjects.textContent =
            data.total_objects;


        // Clear previous results
        detectionList.innerHTML = "";


        // Display detected objects
        data.detections.forEach((detection) => {

            const item = document.createElement("div");

            item.className = "detection-item";


            item.innerHTML = `
                <span>
                    ${detection.class}
                </span>

                <span class="confidence">
                    ${detection.confidence}%
                </span>
            `;


            detectionList.appendChild(item);

        });


        resultsSection.style.display = "grid";

    }

    catch (error) {

        console.error(error);

        statusText.textContent =
            "Something went wrong.";

    }

    finally {

        analyzeBtn.disabled = false;

    }

});