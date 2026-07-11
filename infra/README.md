# Infrastructure — Ringo Treasure Hunt

Bicep templates to deploy the Azure backend services for the Raspbotv2 Treasure Hunt project.

## Resources Deployed

| Resource | Purpose |
|----------|---------|
| Azure OpenAI (gpt-5.4-mini) | Orchestrator agent |
| Azure OpenAI (gpt-5.4) | Vision / camera analysis |
| Azure OpenAI (o3) | Planner agent |
| Azure OpenAI (text-embedding-3-small) | Memory embeddings |
| Azure Speech Services | STT & TTS |
| Azure AI Search | Memory agent vector store |
| Role Assignment | Cognitive Services OpenAI User for SP |

## Authentication

This project uses a **service principal** (Entra ID) to authenticate with Azure OpenAI instead of API keys. The Bicep deployment assigns the `Cognitive Services OpenAI User` role to the service principal on the OpenAI resource.

## Prerequisites

- Azure CLI (`az`) installed and logged in
- A resource group created (default region: `australiaeast`)
- A service principal (app registration) with its **Object ID** (not the App/Client ID)

To find the SP Object ID:
```bash
az ad sp show --id <CLIENT_ID> --query id -o tsv
```

## Deploy

```bash
# Create resource group (if needed)
az group create --name rg-ringo --location australiaeast

# Deploy infrastructure
az deployment group create \
  --resource-group rg-ringo \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```

## After Deployment

Populate your `.env` file with:

```bash
# OpenAI endpoint
az cognitiveservices account show --name ringo-openai --resource-group rg-ringo --query properties.endpoint -o tsv

# Speech key (still uses key-based auth)
az cognitiveservices account keys list --name ringo-speech --resource-group rg-ringo --query key1 -o tsv

# Search endpoint & key
az search admin-key show --service-name ringo-search --resource-group rg-ringo --query primaryKey -o tsv
```

Then set the service principal credentials in `.env`:
```
AZURE_SP_TENANT_ID=<your-tenant-id>
AZURE_SP_CLIENT_ID=<your-client-id>
AZURE_SP_CLIENT_SECRET=<your-client-secret>
```

## Customisation

Edit `main.bicepparam` to change region, SKU tiers, model capacities, or the service principal Object ID.
