export interface User {
  id: string;
  email: string;
  created_at: string | null;
}

export interface UserCreateRequest {
  email: string;
}

export interface UserResponse {
  user_id: string;
  email: string;
}
