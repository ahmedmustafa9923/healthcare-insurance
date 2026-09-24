FROM python:3.11.10-alpine3.20
WORKDIR /app
COPY 1_providers_and_facilities/ /app/1_providers_and_facilities/
COPY 2_insurance_operations/ /app/2_insurance_operations/
COPY 3_crm_and_patients/ /app/3_crm_and_patients/
COPY 4_underwriting_finance/ /app/4_underwriting_finance/
COPY app.py /app/app.py
EXPOSE 8080
RUN adduser -D devopsuser && chown -R devopsuser:devopsuser /app
USER devopsuser
CMD ["python", "app.py"]


