variable "DOCENT_HOST" {
  default = "http://localhost"
}

variable "DOCENT_SERVER_PORT" {
  default = "8888"
}

group "default" {
  targets = ["backend", "frontend"]
}

target "backend" {
  dockerfile = "Dockerfile.backend"
  context    = "."
  tags       = ["docent-backend"]
}

target "frontend" {
  dockerfile = "Dockerfile.frontend"
  context    = "."
  tags       = ["docent-frontend"]
  args = {
    NEXT_PUBLIC_API_HOST = "${DOCENT_HOST}:${DOCENT_SERVER_PORT}"
  }
}
