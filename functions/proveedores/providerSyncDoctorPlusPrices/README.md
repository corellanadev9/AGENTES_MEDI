# providerSyncDoctorPlusPrices

Agente simple para completar `PROVIDER_SERVICE_PRICE.SERVICE_PS_CODE` a partir de
la descripcion de cada estudio de precios Doctor Plus.

## Restricciones

- Usa exclusivamente el indice interno `CODIGO MEDICAL FEES.xlsx`.
- No carga ni consulta `MEDICAL-FEES-DATA.pdf`.
- No recibe ni consulta `CPT_PRODUCT`.
- No modifica el agente existente `providerSyncHomologador`.
- Acepta hasta 200 descripciones por solicitud.
- Solo devuelve codigos presentes entre los candidatos verificados del Excel.

## Endpoint

```text
provider_sync_doctor_plus_prices_api
```

Metodo `POST`:

```json
{
  "rows": [
    {
      "rowNumber": 1,
      "codigoServicio": "701001",
      "nombreServicio": "MAXILAR INFERIOR O SUPERIOR"
    }
  ]
}
```

`codigoServicio` es el codigo Omega. La respuesta `codigoProviderSync` es el
codigo Medical Fees que ProviderSync guarda en `SERVICE_PS_CODE`.

Cuando una fila queda asociada, el item de respuesta tambien incluye
`servicePsDescription`, tomado del nombre exacto del candidato Medical Fees
verificado. Ese valor tambien se devuelve como `nombreMedicalFees`, por
compatibilidad. Si no hay una asociacion verificada, `servicePsDescription` se
omite de la respuesta; ProviderSync debe guardar ese campo como `NULL`.
