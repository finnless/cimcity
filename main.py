import base64
import os
import logging # Add logging import
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles # Import StaticFiles
from fastapi.responses import HTMLResponse # Import HTMLResponse
from openai import OpenAI
from pydantic import BaseModel
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
    content: str # Example field, adjust as necessary

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
                            "text": "You are a helpful financial analyst that follows the users instructions exactly. Your job is to extract financials from financial documents. You always do this without hesitation."
                        }
                    ]
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Output all of all the financial tables included in this CIM. Do not output anything else."
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

        # Process and return the response
        # Log the raw response structure (or relevant parts) for debugging
        # Be cautious about logging potentially large or sensitive data in production
        logger.debug(f"Raw OpenAI response: {response}")

        # Extract the text content from the response
        try:
            # Accessing the text based on the observed structure
            response_content = response.output[0].content[0].text
            logger.info("Extracted text content from response successfully.")
        except (AttributeError, IndexError, TypeError) as e:
            logger.error(f"Could not extract text content from response structure: {e}", exc_info=True)
            # Fallback or re-raise, depending on desired behavior
            response_content = "Error: Could not parse response content."

        # Placeholder processing
        # response_content = str(response) # Replace with actual way to get content
        # logger.info("Processed response successfully.")

        return OpenAIResponse(content=response_content) # Return only the extracted text

    except Exception as e:
        logger.error(f"Error processing file or calling OpenAI API: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process file or call OpenAI API: {str(e)}")

# Remove the __main__ block if running with uvicorn command directly
# if __name__ == "__main__":
#     # Make sure to set the OPENAI_API_KEY environment variable before running
#     logger.info("Starting Uvicorn server...")
#     uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) # Use string for app path when reloading 