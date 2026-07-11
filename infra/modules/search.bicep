@description('Azure AI Search resource name')
param name string

@description('Azure region')
param location string

@description('SKU name')
param sku string

@description('Search index name (for reference — index is created at app level)')
param indexName string

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: name
  location: location
  sku: {
    name: sku
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
  }
  tags: {
    indexName: indexName
  }
}

output endpoint string = 'https://${search.name}.search.windows.net'
output name string = search.name
