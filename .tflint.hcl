config {
  call_module_type = "local"   # lint our own modules too, not just the root
}

plugin "terraform" {
  enabled = true
  preset  = "recommended"      # version pins, unused code, typed variables, deprecated syntax
}
