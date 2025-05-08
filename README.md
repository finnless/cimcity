# CIM CITY: Unlocking CIMs

![CIM CITY Logo](static/cimcitylogo.png)

## Overview

CIM CITY automates extracting financial tables from Confidential Information Memoranda (CIMs), typically PDF documents used in private deals. It helps buy-side analysts by reducing manual data entry, allowing them to focus on analysis. Users upload a PDF, and the tool extracts financial data, presenting it as HTML tables and a downloadable Excel file.

## Features

*   **PDF Upload:** Easy drag-and-drop or file selection for CIMs.
*   **AI-Powered Extraction:** Uses AI (e.g., GPT-4o) to find and structure financial tables.
*   **Structured Output:** Ensures AI returns data in a well-defined JSON format.
*   **Data Validation:** Checks for consistent column lengths in tables.
*   **HTML Display:** Shows extracted tables in the web interface.
*   **Excel Export:** Downloads tables in an Excel file, each table on a separate sheet.
*   **Logging:** Backend logging for monitoring and debugging.

## Technology Stack

*   **Backend:** Python 3.x, FastAPI, Uvicorn, OpenAI client, Pydantic, Pandas, `python-multipart`, `xlsxwriter`.
*   **Frontend:** HTML5, TailwindCSS, Vanilla JavaScript.
*   **Development:** Git & GitHub.

## Project Structure

```
.
├── main.py             # FastAPI application, Pydantic models, AI interaction, PDF processing logic
├── static/
│   ├── index.html      # Frontend HTML structure and JavaScript logic
│   ├── cimcitylogo.png # Project logo
│   └── *.xlsx          # Generated Excel files are temporarily stored here and served from here
├── requirements.txt    # Python project dependencies
└── README.md           # This file
```

## Setup and Running the Application

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd cimcity
    ```

2.  **Create virtual environment & install dependencies:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Windows: venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Set OpenAI API Key:**
    ```bash
    export OPENAI_API_KEY="your_openai_api_key_here"
    # Windows: set OPENAI_API_KEY="your_openai_api_key_here"
    ```

4.  **Run the application:**
    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    ```

5.  **Access:** Open `http://localhost:8000` in your browser.

## API Endpoint

### `POST /extract_financials/`

*   **Description:** Upload a PDF to extract financial tables. Returns HTML tables and an Excel download link.
*   **Request:** `multipart/form-data` with `file` (the PDF).
*   **Response (`APIResponse` model):**
    *   `html_tables` (List[str]): HTML strings for each table.
    *   `excel_file_path` (str | None): Path to the Excel file (e.g., `/static/financial_tables.xlsx`).
*   **Errors:**
    *   `400 Bad Request`: Invalid file type or AI refusal.
    *   `500 Internal Server Error`: Server-side issues (validation, file generation, etc.).

## How it Works

1.  **Upload:** User uploads a PDF via the web page.
2.  **Processing:** The backend receives the file, encodes it, and prepares a request for the AI.
3.  **AI Extraction:** The AI is instructed to find all financial tables and return them in a specific JSON structure.
4.  **Parsing & Validation:** The AI's response is parsed and validated against a Pydantic model.
5.  **Data to DataFrame:** Extracted tables are converted into Pandas DataFrames, with checks for data integrity.
6.  **Output Generation:**
    *   **Excel:** DataFrames are saved into an Excel file in the `static/` directory.
    *   **HTML:** DataFrames are converted to HTML tables.
7.  **Response:** The API sends back the HTML tables and the Excel file path to the frontend for display.
