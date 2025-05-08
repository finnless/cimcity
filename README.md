# CIM CITY: Unlocking CIMs

## Overview

CIM CITY is a tool designed to automate the initial stages of financial analysis for buy-side analysts. It focuses on ingesting Confidential Information Memoranda (CIMs) – typically dense PDF documents shared during private deal processes – and extracting key financial tables. By automatically populating initial data points, CIM CITY aims to reduce manual data entry, allowing analysts to focus more on their core analysis and "doing their magic."

The application provides a simple web interface for users to upload PDF CIMs. The backend then processes these documents, leveraging AI to identify and structure financial data, which is then presented back to the user as viewable HTML tables and a downloadable Excel spreadsheet.

## Features

*   **PDF Upload:** User-friendly drag-and-drop interface or standard file selection for uploading CIMs in PDF format.
*   **AI-Powered Financial Table Extraction:** Utilizes an AI model (configurable, e.g., GPT-4o) to parse documents and extract financial tables.
*   **Structured Data Output:** Employs Pydantic models to ensure the AI returns data in a structured JSON format, specifically designed to represent financial tables with columns and corresponding values.
*   **Data Validation:** Includes checks for data integrity, such as ensuring all columns within an extracted table have the same number of rows.
*   **HTML Table Display:** Presents the extracted financial tables directly in the web interface for quick review.
*   **Excel Export:** Allows users to download the extracted tables as a well-formatted Excel file, with each table in a separate sheet.
*   **Static File Serving:** Serves the frontend application and generated Excel files.
*   **Logging:** Comprehensive logging throughout the backend processes for monitoring and debugging.

## Technology Stack

*   **Backend:**
    *   Python 3.x
    *   FastAPI: For building the web API.
    *   Uvicorn: ASGI server for FastAPI.
    *   OpenAI Python client library (or a compatible interface for `client.responses.parse`): For interacting with the AI model for table extraction.
    *   Pydantic: For data validation and settings management (defining the structure for AI output).
    *   Pandas: For data manipulation and creating Excel files.
    *   `python-multipart`: For handling file uploads with FastAPI.
    *   `xlsxwriter`: Engine for Pandas to write Excel files.
*   **Frontend:**
    *   HTML5
    *   TailwindCSS: For styling the user interface.
    *   Vanilla JavaScript: For client-side interactions, file handling, and API communication.
*   **Development/Other:**
    *   Git & GitHub: For version control.

## Project Structure

```
.
├── main.py             # FastAPI application, Pydantic models, AI interaction, PDF processing logic
├── static/
│   ├── index.html      # Frontend HTML structure and JavaScript logic
│   ├── cimcitylogo.png # Project logo
│   └── *.xlsx          # Generated Excel files are temporarily stored here and served from here
├── requirements.txt    # Python project dependencies (to be created)
└── README.md           # This file
```

## Setup and Running the Application

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd cimcity # Or your project directory name
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up Environment Variables:**
    The application requires an OpenAI API key to function. Set this environment variable:
    ```bash
    export OPENAI_API_KEY="your_openai_api_key_here"
    ```
    On Windows, use `set OPENAI_API_KEY="your_openai_api_key_here"`.

5.  **Run the application:**
    The `main.py` file is set up to be run with Uvicorn.
    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    ```
    The `--reload` flag is useful for development as it automatically reloads the server when code changes are detected.

6.  **Access the application:**
    Open your web browser and navigate to `http://localhost:8000`.

## API Endpoint

### `POST /extract_financials/`

*   **Description:** Accepts a PDF file, processes it to extract financial tables using an AI model, and returns the tables in HTML format along with a link to download an Excel file.
*   **Request:**
    *   `Content-Type: multipart/form-data`
    *   `file`: The PDF file to be processed.
*   **Response (`APIResponse` model):**
    *   `html_tables` (List[str]): A list of HTML strings, each representing an extracted financial table.
    *   `excel_file_path` (str | None): A URL path to the generated Excel file (e.g., `/static/financial_tables_document_name.xlsx`). Returns `null` if no tables were extracted or an error occurred.
*   **Error Handling:**
    *   `400 Bad Request`: If the uploaded file is not a PDF or if the AI refuses the request (e.g., due to content policy).
    *   `500 Internal Server Error`: For issues like Pydantic validation errors against the AI's output, failures in creating or saving the Excel file, or other unexpected server-side errors.

## How it Works

1.  **File Upload:** The user uploads a PDF document through the `static/index.html` page.
2.  **Backend Reception:** The FastAPI backend receives the file at the `/extract_financials/` endpoint.
3.  **Content Processing:**
    *   The file content is read and encoded to base64 to be sent to the AI.
    *   A system prompt is constructed, instructing the AI to act as a financial analyst and extract all tables, adhering to the `ExtractedFinancials` Pydantic schema. This schema defines that the output should be a list of tables, where each table has a name and a list of columns, and each column has a name and a list of values. A critical instruction is to ensure all value lists within a single table have the same length.
4.  **AI Interaction:**
    *   The request (system prompt, user instruction, and file data) is sent to an OpenAI model (e.g., "gpt-4o") using `client.responses.parse` (note: this specific method might be part of a custom OpenAI client wrapper or a placeholder for the intended API call, as the standard library uses different methods for chat completions or other specific tasks).
    *   The `text_format` parameter is set to `ExtractedFinancials`, indicating that the AI's response should be directly parsable into this Pydantic model.
5.  **Response Parsing & Validation:**
    *   The AI's JSON response is parsed into the `ExtractedFinancials` Pydantic model. This automatically validates the structure of the response.
    *   If validation fails or no tables are extracted, an appropriate response or error is logged and returned.
6.  **DataFrame Creation:**
    *   Each extracted table (conforming to the `FinancialTable` and `ColumnData` Pydantic models) is processed.
    *   The list-of-columns structure is converted into a dictionary suitable for creating a Pandas DataFrame.
    *   An additional check is performed to ensure column length consistency within each table before DataFrame creation. Tables failing this check are skipped.
7.  **Output Generation:**
    *   **Excel File:** If DataFrames are successfully created, they are written to an Excel file using `pandas.ExcelWriter` with `xlsxwriter` engine. Each DataFrame becomes a sheet in the Excel workbook. The file is saved in the `static/` directory and a download path is generated.
    *   **HTML Tables:** Each DataFrame is converted to an HTML table string.
8.  **Response to Client:** The API returns a JSON object containing the list of HTML table strings and the path to the downloadable Excel file. The frontend JavaScript then renders the HTML tables and displays the download link.
