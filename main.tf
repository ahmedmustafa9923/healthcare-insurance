module "blue_cross_personal" {
 source = "./terraform_modules/carrier_app"
 carrier_name = "blue-cross"
 line_of_business = "personal"
 }

module "blue_cross_business" {
 source = "./terraform_modules/carrier_app"
 carrier_name = "blue-cross"
 line_of_business = "business"
 }

module "hartford_personal"   {
 source = "./terraform_modules/carrier_app" 
 carrier_name = "hartford" 
 line_of_business = "personal"
 }

module "hartford_business"   {
 source = "./terraform_modules/carrier_app"
 carrier_name = "hartford"  
 line_of_business = "business"
 }

module "all_state_personal"  {
 source = "./terraform_modules/carrier_app"
 carrier_name = "all-state" 
 line_of_business = "personal"
 }

module "all_state_business"  {
 source = "./terraform_modules/carrier_app" 
 carrier_name = "all-state" 
 line_of_business = "business"
 }
