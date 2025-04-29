import base64
import os
import logging # Add logging import
import pandas as pd # Add pandas import
import io # Add io import for Excel
import re # Add re import
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles # Import StaticFiles
from fastapi.responses import HTMLResponse # Import HTMLResponse
from openai import OpenAI
from pydantic import BaseModel
import uvicorn

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# It's recommended to load the API key from environment variables
# client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
# For demonstration, initializing client without explicit key (assumes env var is set)
client = OpenAI()

app = FastAPI()

# Mount the static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve the index.html at the root
@app.get("/", response_class=HTMLResponse)
async def read_root():
    try:
        with open("static/index.html", "r") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        logger.error("index.html not found in static directory.")
        raise HTTPException(status_code=500, detail="Frontend file not found.")
    except Exception as e:
        logger.error(f"Error reading index.html: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not load frontend.")

class OpenAIResponse(BaseModel):
    # Define the structure based on the expected OpenAI response
    # This is a placeholder, adjust according to the actual response schema if needed
    html_tables: list[str]
    excel_file_path: str | None # Path might be None if extraction fails

@app.post("/extract_financials/", response_model=OpenAIResponse) # Adjust response_model based on actual API output
async def extract_financials_from_pdf(file: UploadFile = File(...)):
    """
    Accepts a PDF file, converts it to base64, sends it to OpenAI's
    responses.create endpoint, and returns the response.
    """
    logger.info(f"Received request for file: {file.filename} ({file.content_type})")

    if file.content_type != "application/pdf":
        logger.warning(f"Invalid file type received: {file.content_type}")
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDFs are accepted.")

    try:
        logger.info("Reading file content...")
        contents = await file.read()
        logger.info(f"Read {len(contents)} bytes from file.")

        logger.info("Encoding file content to base64...")
        encoded_data = base64.b64encode(contents).decode('utf-8')
        file_data_uri = f"data:application/pdf;base64,{encoded_data}"
        logger.info("File content encoded successfully.") # Avoid logging the full base64 string for brevity

        # Construct the OpenAI API request payload
        request_payload = {
            "model": "gpt-4o",
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "You are a helpful financial analyst. Your job is to extract all financial tables from the provided document. You MUST output ONLY Python code that defines these tables as pandas DataFrames. Enclose the Python code within triple backticks (```python ... ```). Do not include any explanatory text before or after the code block. Define each table as a separate pandas DataFrame variable. \n\n**IMPORTANT:** When creating the dictionary for each DataFrame, ensure that all lists (array values associated with keys) have the exact same number of elements, as this is required by pandas. Double-check the row/column alignment in the source table to ensure data integrity and equal list lengths in your generated code. Import pandas as pd at the beginning of the code block."
                        }
                    ]
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Extract all financial tables from this document and represent them as pandas DataFrames in a single Python code block."
                        },
                        {
                            "type": "input_file",
                            "filename": file.filename, # Use the uploaded file's name
                            "file_data": file_data_uri # Avoid logging the full base64 data here
                        }
                    ]
                },
            ],
            "text": {
                "format": {
                    "type": "text"
                }
            },
            "reasoning": {},
            "tools": [],
            "temperature": 1,
            "max_output_tokens": 4982,
            "top_p": 1,
            "store": True
        }
        # Log payload excluding the potentially large file_data for clarity
        log_payload = {k: v for k, v in request_payload.items() if k != 'input'}
        log_payload['input'] = [
            item if item['role'] != 'user' else 
            {
                'role': item['role'], 
                'content': [c if c['type'] != 'input_file' else {'type': 'input_file', 'filename': c['filename'], 'file_data': '<base64_data_omitted>'} for c in item['content']]
            }
            for item in request_payload['input']
        ]
        logger.info(f"Sending request to OpenAI: {log_payload}")

        # Call the OpenAI API
        response = client.responses.create(**request_payload)
        logger.info("Received response from OpenAI.")
        # Log the raw response structure for debugging
        logger.debug(f"Raw OpenAI response object type: {type(response)}")
        try:
            # Attempt to log response as a dictionary if possible
            logger.debug(f"Raw OpenAI response content: {response.model_dump_json(indent=2)}")
        except AttributeError:
            # Fallback to string representation if model_dump_json is not available
            logger.debug(f"Raw OpenAI response content: {str(response)}")

        # Extract the text content from the response
        try:
            # Accessing the text based on the observed structure
            response_content = response.output[0].content[0].text
            logger.info("Extracted text content from response successfully.")

            # Extract Python code block using regex
            match = re.search(r"```python\n(.*)```", response_content, re.DOTALL)
            if not match:
                logger.error("Could not find Python code block in the response.")
                raise HTTPException(status_code=500, detail="Could not parse Python code from LLM response.")

            python_code = match.group(1).strip()
            logger.debug(f"Extracted Python code:\n{python_code}")

            # Prepare execution environment
            local_namespace = {"pd": pd} # Make pandas available to the executed code
            dataframes = {}
            html_tables = []
            excel_file_path = None

            try:
                exec(python_code, globals(), local_namespace)
                logger.info("Successfully executed extracted Python code.")

                # Find created DataFrames in the namespace
                for name, obj in local_namespace.items():
                    if isinstance(obj, pd.DataFrame):
                        dataframes[name] = obj
                        logger.debug(f"Found DataFrame: {name}")

                if not dataframes:
                    logger.warning("Executed code did not produce any pandas DataFrames.")
                    # Optionally raise error or return empty response
                else:
                    # Generate Excel file
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                        for name, df in dataframes.items():
                            # Use variable name as sheet name, sanitize if needed
                            sheet_name = re.sub(r'[\/*?:[\]]', '_', name) # Basic sanitization
                            sheet_name = sheet_name[:31] # Excel sheet name limit
                            df.to_excel(writer, sheet_name=sheet_name, index=False)
                            logger.debug(f"Wrote DataFrame '{name}' to sheet '{sheet_name}'")
                    excel_buffer.seek(0)

                    # Save Excel to static directory
                    original_filename_base = os.path.splitext(file.filename)[0]
                    safe_filename_base = re.sub(r'[^a-zA-Z0-9_-]', '_', original_filename_base)
                    excel_filename = f"financial_tables_{safe_filename_base}.xlsx"
                    static_excel_path = os.path.join("static", excel_filename)

                    try:
                        with open(static_excel_path, "wb") as f:
                            f.write(excel_buffer.read())
                        excel_file_path = f"/static/{excel_filename}" # Path for frontend
                        logger.info(f"Saved Excel file to: {static_excel_path}")
                    except IOError as e:
                        logger.error(f"Failed to save Excel file '{static_excel_path}': {e}", exc_info=True)
                        raise HTTPException(status_code=500, detail="Failed to save generated Excel file.")

                    # Generate HTML tables
                    for name, df in dataframes.items():
                        # Add some basic styling classes for the HTML table
                        html_table = df.to_html(classes='table table-bordered table-striped', index=False, border=0)
                        # Optionally add a title based on the DataFrame name
                        html_tables.append(f"<h3>{name.replace('_', ' ').title()}</h3>{html_table}")
                    logger.info(f"Generated {len(html_tables)} HTML tables.")

            except ValueError as ve:
                # Specifically catch pandas DataFrame length mismatch error
                if "All arrays must be of the same length" in str(ve):
                    logger.error(f"Pandas ValueError: {ve}. LLM generated code likely had unequal list lengths.", exc_info=True)
                    logger.debug(f"Problematic generated code:\n{python_code}") # Log the bad code for debugging
                    raise HTTPException(
                        status_code=422, # Unprocessable Entity might be appropriate
                        detail="Error: The AI failed to structure table data correctly (column length mismatch). Please verify the table in the source PDF."
                    )
                else:
                    # Re-raise other ValueErrors
                    logger.error(f"Unhandled ValueError during code execution: {ve}", exc_info=True)
                    raise HTTPException(status_code=500, detail=f"Error executing generated code: {ve}")
            except Exception as exec_error:
                logger.error(f"Error executing extracted Python code: {exec_error}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Error executing generated code: {exec_error}")

        except (AttributeError, IndexError, TypeError) as e:
            logger.error(f"Could not extract text content from response structure: {e}", exc_info=True)
            # Ensure response_content is defined for the final return/error message
            response_content = "Error: Could not parse response content."
            # Raise HTTPException here if content extraction fails
            raise HTTPException(status_code=500, detail="Could not parse response content from LLM.")

        # Return the HTML tables and Excel file path
        return OpenAIResponse(html_tables=html_tables, excel_file_path=excel_file_path)

    except HTTPException: # Re-raise HTTPExceptions
        raise
    except Exception as e:
        logger.error(f"Error processing file or calling OpenAI API: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process file or call OpenAI API: {str(e)}")

# Remove the __main__ block if running with uvicorn command directly
# if __name__ == "__main__":
#     # Make sure to set the OPENAI_API_KEY environment variable before running
#     logger.info("Starting Uvicorn server...")
#     uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) # Use string for app path when reloading 