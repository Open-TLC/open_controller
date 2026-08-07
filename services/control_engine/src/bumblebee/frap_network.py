import gymnasium as gym
import torch
from ray.rllib.algorithms.ppo.torch.default_ppo_torch_rl_module import (
    DefaultPPOTorchRLModule,
)
from ray.rllib.core.columns import Columns
from torch import nn
from torch.distributions import Categorical


class FRAPMaskedPPORLModule(DefaultPPOTorchRLModule):
    def setup(self):
        if isinstance(self.action_space, gym.spaces.Discrete):
            self.num_phases: int = int(self.action_space.n)
        else:
            raise ValueError(
                f"Expected Discrete action space, got {type(self.action_space)}",
            )

        hidden_dim = self.model_config.get("hidden_dim", 32)
        embed_dim = self.model_config.get("embed_dim", 16)
        phase_feat_dim = 4

        # Pure PyTorch actor.
        self.actor = FRAPActor(
            num_phases=self.num_phases,
            phase_feat_dim=phase_feat_dim,
            hidden_dim=hidden_dim,
            embed_dim=embed_dim,
        )

        # Critic for PPO training.
        self.value_head = nn.Sequential(
            nn.Linear(self.num_phases * embed_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def _forward(self, batch: dict, **kwargs) -> dict:
        obs = batch[Columns.OBS]
        real_obs = obs["real_obs"].float()
        action_mask = obs["action_mask"].float()
        batch_size = real_obs.shape[0]

        # Get policy logits from actor.
        masked_logits = self.actor(real_obs, action_mask)

        # Compute critic value using actor's phase_encoder embeddings.
        phase_embeddings = self.actor.phase_encoder(real_obs)
        flat_context = phase_embeddings.view(batch_size, -1)
        vf_preds = self.value_head(flat_context).squeeze(-1)

        if vf_preds.ndim == 0:
            vf_preds = vf_preds.unsqueeze(0)

        return {
            Columns.ACTION_DIST_INPUTS: masked_logits,
            Columns.VF_PREDS: vf_preds,
        }

    def compute_values(self, batch: dict, embeddings=None) -> torch.Tensor:
        obs = batch[Columns.OBS]
        real_obs = obs["real_obs"].float()
        batch_size = real_obs.shape[0]

        phase_embeddings = self.actor.phase_encoder(real_obs)
        flat_context = phase_embeddings.view(batch_size, -1)
        vf_preds = self.value_head(flat_context).squeeze(-1)

        if vf_preds.ndim == 0:
            vf_preds = vf_preds.unsqueeze(0)

        return vf_preds

    def get_initial_state(self) -> dict:
        return {}

    def is_stateful(self) -> bool:
        return False

    def _forward_exploration(self, batch: dict, **kwargs) -> dict:
        outs = self._forward(batch, **kwargs)
        logits = outs[Columns.ACTION_DIST_INPUTS]
        dist = Categorical(logits=logits)
        actions = dist.sample()

        outs[Columns.ACTIONS] = actions
        outs[Columns.ACTION_LOGP] = dist.log_prob(actions)
        return outs

    def _forward_inference(self, batch: dict, **kwargs) -> dict:
        outs = self._forward(batch, **kwargs)
        logits = outs[Columns.ACTION_DIST_INPUTS]
        actions = torch.argmax(logits, dim=-1)
        dist = Categorical(logits=logits)

        outs[Columns.ACTIONS] = actions
        outs[Columns.ACTION_LOGP] = dist.log_prob(actions)
        return outs

    def _forward_train(self, batch: dict, **kwargs) -> dict:
        outs = self._forward(batch, **kwargs)
        logits = outs[Columns.ACTION_DIST_INPUTS]
        dist = Categorical(logits=logits)

        if Columns.ACTIONS in batch:
            outs[Columns.ACTION_LOGP] = dist.log_prob(batch[Columns.ACTIONS])
        return outs


class FRAPActor(nn.Module):
    """Pure PyTorch FRAP policy network for traffic signal control inference."""

    def __init__(
        self,
        num_phases: int,
        phase_feat_dim: int = 4,
        hidden_dim: int = 32,
        embed_dim: int = 16,
    ):
        super().__init__()
        self.num_phases = num_phases

        # Phase encoder creates embeddings from per-phase features.
        self.phase_encoder = nn.Sequential(
            nn.Linear(phase_feat_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, embed_dim),
            nn.ReLU(),
        )

        # Competition network compares phase pair embeddings.
        self.competition_network = nn.Sequential(
            nn.Linear(embed_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(
        self,
        real_obs: torch.Tensor,
        action_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Forward pass computing action logits.

        Args:
            real_obs: Traffic observation.
            action_mask: Mask for invalid actions.

        Returns:
            Logits with action mask applied.

        """
        batch_size = real_obs.shape[0]

        # Calculate phase embeddings: [batch_size, num_phases, embed_dim].
        phase_embeddings = self.phase_encoder(real_obs)

        # Build pairwise feature representations.
        h_i = phase_embeddings.unsqueeze(2).expand(
            batch_size,
            self.num_phases,
            self.num_phases,
            -1,
        )
        h_j = phase_embeddings.unsqueeze(1).expand(
            batch_size,
            self.num_phases,
            self.num_phases,
            -1,
        )
        pair_features = torch.cat([h_i, h_j], dim=-1)

        # Compute priority scores matrix.
        competition_matrix = self.competition_network(pair_features).squeeze(-1)
        raw_logits = competition_matrix.sum(dim=-1)

        # Apply internal action masking.
        if action_mask is not None:
            inf_mask = (1.0 - action_mask.float()) * -1e8
            return raw_logits + inf_mask

        return raw_logits
