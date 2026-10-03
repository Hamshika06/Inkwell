import torch
import torch.nn.functional as F


def masked_loss(logits, targets, mask, row_weights, pos_weight):
    """Positive-class weighting only; unknown labels contribute neither loss nor gradient.

    L = sum(w_i m_ic BCEWithLogits(z_ic,y_ic,pos_weight_c)) / sum(w_i m_ic)
    """
    weights = mask * row_weights[:, None]
    denominator = weights.sum()
    if denominator.item() <= 0:
        raise ValueError('Batch has no supervised labels with positive weight')
    return (F.binary_cross_entropy_with_logits(logits, targets, pos_weight=pos_weight,
                                             reduction='none') * weights).sum() / denominator
