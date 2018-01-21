from __future__ import absolute_import

import torch
from torch import nn
from torch.autograd import Variable
# import numpy as np


def euclidean_dist(inputs_):
    # Compute pairwise distance, replace by the official when merged
    n = inputs_.size(0)
    dist = torch.pow(inputs_, 2).sum(dim=1, keepdim=True).expand(n, n)
    dist = dist + dist.t()
    dist.addmm_(1, -2, inputs_, inputs_.t())
    dist = dist.clamp(min=1e-12).sqrt()  # for numerical stability
    return dist


class NeighbourLoss(nn.Module):
    def __init__(self, margin=0.1):
        super(NeighbourLoss, self).__init__()
        self.margin = margin
        self.ranking_loss = nn.MarginRankingLoss(margin=self.margin)

    def forward(self, inputs, targets):
        n = inputs.size(0)
        # Compute pairwise distance, replace by the official when merged
        dist_mat = euclidean_dist(inputs)
        targets = targets.cuda()
        # split the positive and negative pairs
        eyes_ = Variable(torch.eye(n, n)).cuda()
        # eyes_ = Variable(torch.eye(n, n))
        pos_mask = targets.expand(n, n).eq(targets.expand(n, n).t())
        neg_mask = eyes_.eq(eyes_) - pos_mask
        pos_mask = pos_mask - eyes_.eq(1)

        pos_dist = torch.masked_select(dist_mat, pos_mask)
        neg_dist = torch.masked_select(dist_mat, neg_mask)

        num_instances = len(pos_dist)//n + 1
        num_neg_instances = n - num_instances

        pos_dist = pos_dist.resize(len(pos_dist)//(num_instances-1), num_instances-1)
        neg_dist = neg_dist.resize(
            len(neg_dist) // num_neg_instances, num_neg_instances)

        #  clear way to compute the loss first
        loss = list()
        # prec = list()
        err = 0
        num_hard_pos = 0

        for i, pos_pair in enumerate(pos_dist):

            pos_pair = torch.sort(pos_pair)[0]
            neg_pair = torch.sort(neg_dist[i])[0]
            #
            # # neg_threshold = neg_pair[int(num_neg_instances*0.8)]
            # # hard_pos_pair = torch.masked_select(pos_pair, pos_pair > neg_threshold)
            # # if len(hard_pos_pair) > 0:
            #     # print('number of hard positive is: %03d' % len(hard_pos_pair))
            #     pos_loss = torch.mean(hard_pos_pair)
            #     num_hard_pos += len(hard_pos_pair)
            # else:
            #     pos_loss = 0

            pos_min = pos_pair[0]
            neg_pair = torch.masked_select(neg_pair, neg_pair < pos_min + 0.1)
            if len(neg_pair) > 0:
                loss.append(pos_min - torch.mean(neg_pair) + 0.1 )
                err += 1

        if len(loss) == 0:
            loss = 0.0 * (torch.mean(pos_min))
        else:
            loss = torch.sum(torch.cat(loss))/n
        prec = 1 - float(err)/n
        neg_d = torch.mean(neg_dist).data[0]
        pos_d = torch.mean(pos_dist).data[0]
        print('number of hard positive is: %03d' % num_hard_pos)
        return loss, prec, pos_d, neg_d


def main():
    data_size = 32
    input_dim = 3
    output_dim = 2
    num_class = 4
    # margin = 0.5
    x = Variable(torch.rand(data_size, input_dim), requires_grad=False)
    w = Variable(torch.rand(input_dim, output_dim), requires_grad=True)
    # print('training data is ', x)
    # print('initial parameters are ', w)
    inputs = x.mm(w)
    # print('extracted feature is :', inputs)

    # y_ = np.random.randint(num_class, size=data_size)
    y_ = 8*list(range(num_class))
    targets = Variable(torch.IntTensor(y_))

    print(NeighbourLoss(margin=0.1)(inputs, targets))


if __name__ == '__main__':
    main()
    print('Congratulations to you!')