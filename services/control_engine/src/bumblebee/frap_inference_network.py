import os

import numpy as np
import torch

from .frap_network import FRAPActor


class FRAPInferenceModel:
    """Wrapper for running standalone PyTorch FRAP inference."""

    def __init__(
        self,
        weights_path: str,
        num_phases: int,
        hidden_dim: int = 32,
        embed_dim: int = 16,
        device: str = "cpu",
    ) -> None:
        self.device = device
        self.model = FRAPActor(
            num_phases=num_phases,
            phase_feat_dim=4,
            hidden_dim=hidden_dim,
            embed_dim=embed_dim,
        )

        if not os.path.exists(weights_path):
            raise FileNotFoundError(f"Model file not found at: {weights_path}")

        # Load weights.
        state_dict = torch.load(weights_path, map_location=device)
        self.model.load_state_dict(state_dict)
        self.model.to(device)
        self.model.eval()

    def predict(self, obs_dict: dict[str, np.ndarray]) -> int:
        """Predict the best phase index to take.

        Args:
            obs_dict: Dictionary containing "real_obs" and "action_mask".

        Returns:
            The selected discrete phase action index.

        """
        # Convert NumPy arrays to PyTorch tensors.
        real_obs_tensor = (
            torch.from_numpy(obs_dict["real_obs"]).float().unsqueeze(0).to(self.device)
        )
        action_mask_tensor = (
            torch.from_numpy(obs_dict["action_mask"])
            .float()
            .unsqueeze(0)
            .to(self.device)
        )

        with torch.no_grad():
            # FRAPActor handles internal masking via action_mask
            logits = self.model(real_obs_tensor, action_mask_tensor)
            return int(torch.argmax(logits, dim=-1).item())


def load_model(
    model_file: str,
    num_phases: int,
    hidden_dim: int = 32,
    embed_dim: int = 16,
) -> FRAPInferenceModel:
    """Load inference model from file."""
    return FRAPInferenceModel(
        weights_path=model_file,
        num_phases=num_phases,
        hidden_dim=hidden_dim,
        embed_dim=embed_dim,
    )
