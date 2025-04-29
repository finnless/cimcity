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
from pydantic import BaseModel, Field, ValidationError, validator # Import validator
from typing import List, Dict, Any # Import List and Dict
import uvicorn

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# It's recommended to load the API key from environment variables
# client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
# For demonstration, initializing client without explicit key (assumes env var is set)
client = OpenAI()

app = FastAPI()

# --- Pydantic Models for Structured Output ---
class ColumnData(BaseModel):
    """Represents a single column in a financial table."""
    column_name: str = Field(..., description="The header/name of the column.")
    values: List[str | int | float | None] = Field(..., description="The list of data points in this column. All 'values' lists within a single table's 'columns' must have the same length.")

class FinancialTable(BaseModel):
    """Represents a single financial table extracted from the document."""
    table_name: str = Field(..., description="A descriptive name for the financial table (e.g., 'Income Statement Q1 2023', 'Balance Sheet'). Use underscores instead of spaces.")
    # Changed from Dict to List of ColumnData objects
    columns: List[ColumnData] = Field(..., description="The columns of the table, represented as a list of objects, each containing a 'column_name' and its 'values' list. **CRITICAL: Ensure all 'values' lists within this table have the same length.**")

    # Removed the validator here, will validate lengths after reconstructing the dict for pandas

class ExtractedFinancials(BaseModel):
    """The overall structure for extracted financial tables."""
    tables: List[FinancialTable]

# --- FastAPI Setup ---

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

class APIResponse(BaseModel):
    """Response model for the API endpoint"""
    html_tables: list[str]
    excel_file_path: str | None # Path might be None if extraction fails

@app.post("/extract_financials/", response_model=APIResponse)
async def extract_financials_from_pdf(file: UploadFile = File(...)):
    """
    Accepts a PDF file, sends it to OpenAI's responses.parse endpoint
    using a Pydantic schema for structured output, processes the result
    into DataFrames, and returns HTML tables and an Excel file path.
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
        logger.info("File content encoded successfully.")

        # Updated system prompt for structured output using list of columns - Enhanced for ALL tables
        system_prompt = """You are an expert financial analyst AI. Your primary task is to meticulously extract **ALL** financial tables present in the provided document, without exception.
Search the entire document thoroughly.
You MUST output the extracted data in JSON format adhering strictly to the provided 'ExtractedFinancials' schema.
Each distinct financial table found must be represented as a separate object within the top-level 'tables' list.
Each table object requires:
1.  'table_name': A descriptive string name for the table (e.g., 'Consolidated Balance Sheet').
2.  'columns': A list of column objects.
Each column object requires:
1.  'column_name': The string header of the column.
2.  'values': A list containing the data points for that column.

**CRITICAL REQUIREMENT:** For every table extracted, ensure that all the 'values' lists within its 'columns' list have the exact same number of elements. Data integrity depends on this. Double-check row/column alignment in the source table carefully.

Output ONLY the valid JSON object conforming to the schema. Do not include any introductory text, explanations, or summaries outside the JSON structure. Find and extract **ALL** tables."""

        logger.info("Sending request to OpenAI for structured parsing...")
        response = client.responses.parse(
            model="gpt-4o",
            input=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Extract all financial tables from this document according to the specified JSON schema."
                        },
                        {
                            "type": "input_file",
                            "filename": file.filename,
                            "file_data": file_data_uri
                        }
                    ]
                },
            ],
            text_format=ExtractedFinancials, # Use the updated Pydantic model
            max_output_tokens=4096,
            temperature=0.4 # Increased temperature slightly
        )
        logger.info("Received response from OpenAI.")

        if response.status != "completed":
             incomplete_reason = response.incomplete_details.reason if response.incomplete_details else "unknown"
             logger.error(f"OpenAI response was not completed. Status: {response.status}, Reason: {incomplete_reason}")
             if response.output and response.output[0].content and response.output[0].content[0].type == "refusal":
                 refusal_message = response.output[0].content[0].refusal
                 logger.warning(f"OpenAI refused the request: {refusal_message}")
                 raise HTTPException(status_code=400, detail=f"AI refused the request: {refusal_message}")
             raise HTTPException(status_code=500, detail=f"AI response incomplete: {incomplete_reason}")

        extracted_data: ExtractedFinancials = response.output_parsed
        if not extracted_data or not extracted_data.tables:
             logger.warning("OpenAI response parsed, but no financial tables were extracted.")
             return APIResponse(html_tables=[], excel_file_path=None)

        logger.info(f"Successfully parsed {len(extracted_data.tables)} financial tables from OpenAI response.")

        dataframes = {}
        html_tables = []
        excel_file_path = None

        # Process the structured data (list of columns) into DataFrames
        for table in extracted_data.tables:
            table_name = table.table_name
            logger.debug(f"Processing extracted table: '{table_name}'")

            # Reconstruct dictionary for DataFrame from the list of columns
            table_data_dict = {}
            if not table.columns:
                logger.warning(f"Table '{table_name}' has no columns defined in the response. Skipping.")
                continue

            try:
                column_lengths = set()
                for col in table.columns:
                    table_data_dict[col.column_name] = col.values
                    column_lengths.add(len(col.values))

                # Check for length consistency AFTER building the dictionary
                if len(column_lengths) > 1:
                    logger.error(f"Pandas ValueError for table '{table_name}': Column lengths are inconsistent: {column_lengths}. LLM failed structure requirement.", exc_info=False) # No need for full stack trace here
                    logger.debug(f"Problematic columns data for table '{table_name}': {table.columns}")
                    # Skip this table
                    continue
                elif not column_lengths: # Handle case where columns might be empty lists, technically consistent but not useful
                     logger.warning(f"Table '{table_name}' columns have zero length. Skipping DataFrame creation.")
                     continue

                # Create DataFrame
                df = pd.DataFrame(table_data_dict)
                dataframes[table_name] = df
                logger.debug(f"Successfully created DataFrame for '{table_name}' with shape {df.shape}")

            except Exception as df_err:
                # Catch potential errors during dict reconstruction or DataFrame creation
                logger.error(f"Unexpected error processing columns or creating DataFrame for table '{table_name}': {df_err}", exc_info=True)
                # Skip this table on error
                continue


        # --- Generate Excel and HTML (No changes needed here) ---
        if not dataframes:
             logger.warning("No valid DataFrames were created from the extracted data.")
             return APIResponse(html_tables=[], excel_file_path=None)
        else:
            try:
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                    for name, df in dataframes.items():
                        sheet_name = re.sub(r'[\\/*?:[\]]', '_', name)
                        sheet_name = sheet_name[:31]
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                        logger.debug(f"Wrote DataFrame '{name}' to sheet '{sheet_name}'")
                excel_buffer.seek(0)

                original_filename_base = os.path.splitext(file.filename)[0]
                safe_filename_base = re.sub(r'[^a-zA-Z0-9_-]', '_', original_filename_base)
                excel_filename = f"financial_tables_{safe_filename_base}.xlsx"
                static_excel_path = os.path.join("static", excel_filename)

                with open(static_excel_path, "wb") as f:
                    f.write(excel_buffer.read())
                excel_file_path = f"/static/{excel_filename}"
                logger.info(f"Saved Excel file to: {static_excel_path}")

                for name, df in dataframes.items():
                    html_table = df.to_html(classes='table table-bordered table-striped', index=False, border=0)
                    html_tables.append(f"<h3>{name.replace('_', ' ').title()}</h3>{html_table}")
                logger.info(f"Generated {len(html_tables)} HTML tables.")

            except IOError as e:
                logger.error(f"Failed to save Excel file '{static_excel_path}': {e}", exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to save generated Excel file.")
            except Exception as output_err:
                 logger.error(f"Failed during Excel/HTML generation: {output_err}", exc_info=True)
                 raise HTTPException(status_code=500, detail="Failed to generate output files.")


        return APIResponse(html_tables=html_tables, excel_file_path=excel_file_path)

    except ValidationError as e:
        logger.error(f"Pydantic validation failed for OpenAI response: {e}", exc_info=True)
        logger.debug(f"Raw OpenAI output causing validation error: {response.output_text if 'response' in locals() and hasattr(response, 'output_text') else 'N/A'}")
        raise HTTPException(status_code=500, detail=f"AI response did not match expected structure: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in /extract_financials/: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


# Remove the __main__ block if running with uvicorn command directly
# if __name__ == "__main__":
#     # Make sure to set the OPENAI_API_KEY environment variable before running
#     logger.info("Starting Uvicorn server...")
#     uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 