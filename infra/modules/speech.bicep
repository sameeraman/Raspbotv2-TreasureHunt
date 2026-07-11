@description('Azure Speech Services resource name')
param name string

@description('Azure region')
param location string

@description('SKU name')
param sku string

@description('Object ID of the service principal for role assignment')
param servicePrincipalObjectId string

// Cognitive Services Speech User role definition ID
var cognitiveServicesSpeechUserRoleId = 'f2dc8367-1007-4938-bd23-fe263f013447'

resource speech 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  kind: 'SpeechServices'
  sku: {
    name: sku
  }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

// Grant the service principal "Cognitive Services Speech User" role on the Speech resource
resource speechRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(speech.id, servicePrincipalObjectId, cognitiveServicesSpeechUserRoleId)
  scope: speech
  properties: {
    principalId: servicePrincipalObjectId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesSpeechUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

output name string = speech.name
output region string = speech.location
output resourceId string = speech.id
