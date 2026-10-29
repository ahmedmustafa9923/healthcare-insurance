variable "carrier_name" {
  description = "The name of the insurance carrier (lowercase, hyphenated, e.g. blue-cross)"
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}[a-z0-9]$", var.carrier_name))
    error_message = "carrier_name must be 3-22 lowercase letters, digits or hyphens (e.g. blue-cross)."
  }
}

variable "line_of_business" {
  description = "The line of business (personal or business)"
  type        = string

  validation {
    condition     = contains(["personal", "business"], var.line_of_business)
    error_message = "line_of_business must be \"personal\" or \"business\"."
  }
}
